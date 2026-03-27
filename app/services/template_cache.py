"""
Template Cache Service

This module provides caching functionality for Word templates used in PDF generation.
Templates are cached on the filesystem with metadata stored in Redis.
Cache entries have their TTL refreshed on each access.
"""

import os
import json
import shutil
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import redis

logger = logging.getLogger(__name__)

# Redis key prefix for template cache metadata
CACHE_KEY_PREFIX = "template_cache:"


def get_redis_client() -> redis.Redis:
    """
    Get Redis client using the same connection as Celery.

    Returns:
        Redis client instance

    Raises:
        Exception: If Redis connection cannot be established
    """
    redis_url = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0")
    return redis.from_url(redis_url, decode_responses=True)


def get_cache_config() -> Dict[str, Any]:
    """
    Get cache configuration from environment variables.

    Returns:
        Dictionary with cache configuration
    """
    return {
        "enabled": os.environ.get("TEMPLATE_CACHE_ENABLED", "true").lower() == "true",
        "cache_dir": os.environ.get("TEMPLATE_CACHE_DIR", "/app/template_cache"),
        "max_size_mb": int(os.environ.get("TEMPLATE_CACHE_MAX_SIZE_MB", 500)),
        "ttl_days": int(os.environ.get("TEMPLATE_CACHE_TTL_DAYS", 7)),
    }


def get_cache_path(template_hash: str) -> str:
    """
    Get the filesystem path for a cached template.

    Args:
        template_hash: Client-provided hash identifying the template

    Returns:
        Full path to the cached template file
    """
    config = get_cache_config()
    cache_dir = config["cache_dir"]
    # Use the hash directly as filename with .docx extension
    return os.path.join(cache_dir, f"{template_hash}.docx")


def _get_redis_key(template_hash: str) -> str:
    """
    Get the Redis key for a template hash.

    Args:
        template_hash: Client-provided hash identifying the template

    Returns:
        Redis key string
    """
    return f"{CACHE_KEY_PREFIX}{template_hash}"


def check_cache(template_hash: str) -> Optional[Dict[str, Any]]:
    """
    Check if a template exists in the cache.

    Validates both Redis metadata and filesystem file existence.

    Args:
        template_hash: Client-provided hash identifying the template

    Returns:
        Cache metadata dict if found and valid, None otherwise
    """
    config = get_cache_config()

    if not config["enabled"]:
        logger.debug("Template cache is disabled")
        return None

    try:
        client = get_redis_client()
        redis_key = _get_redis_key(template_hash)

        # Get metadata from Redis
        metadata_json = client.get(redis_key)
        if not metadata_json:
            logger.debug(
                f"Template cache MISS (no Redis entry) for hash: {template_hash}"
            )
            return None

        metadata = json.loads(metadata_json)
        file_path = metadata.get("file_path")

        # Validate file exists on filesystem
        if not file_path or not os.path.exists(file_path):
            logger.warning(
                f"Template cache STALE (file missing) for hash: {template_hash}, "
                f"removing Redis entry"
            )
            client.delete(redis_key)
            return None

        # Validate file size > 0
        if os.path.getsize(file_path) == 0:
            logger.warning(
                f"Template cache CORRUPT (empty file) for hash: {template_hash}, "
                f"removing cache entry"
            )
            _delete_cache_entry(template_hash)
            return None

        logger.info(f"Template cache HIT for hash: {template_hash}")
        return metadata

    except redis.RedisError as e:
        logger.error(f"Redis error checking cache for hash {template_hash}: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in cache metadata for hash {template_hash}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error checking cache for hash {template_hash}: {e}")
        return None


def store_template(template_hash: str, source_path: str) -> Optional[str]:
    """
    Store a template in the cache.

    Copies the template file to the cache directory and stores metadata in Redis.
    Uses atomic write (temp file + rename) for safe concurrent access.

    Args:
        template_hash: Client-provided hash identifying the template
        source_path: Path to the template file to cache

    Returns:
        Path to the cached file, or None if caching failed
    """
    config = get_cache_config()

    if not config["enabled"]:
        logger.debug("Template cache is disabled, skipping store")
        return None

    cache_dir = config["cache_dir"]
    ttl_days = config["ttl_days"]
    temp_path = None
    cache_path = None

    try:
        # Ensure cache directory exists
        os.makedirs(cache_dir, exist_ok=True)

        cache_path = get_cache_path(template_hash)
        temp_path = f"{cache_path}.tmp.{os.getpid()}"

        # Copy file to temp location first (atomic write pattern)
        shutil.copy2(source_path, temp_path)

        # Atomic rename
        os.rename(temp_path, cache_path)

        # Get file size
        file_size = os.path.getsize(cache_path)

        # Store metadata in Redis
        now = datetime.now(timezone.utc).isoformat()
        metadata = {
            "file_path": cache_path,
            "file_size": file_size,
            "created_at": now,
            "last_accessed": now,
            "access_count": 1,
        }

        client = get_redis_client()
        redis_key = _get_redis_key(template_hash)

        # Set with TTL (in seconds)
        ttl_seconds = ttl_days * 24 * 60 * 60
        client.setex(redis_key, ttl_seconds, json.dumps(metadata))

        logger.info(
            f"Template stored in cache: hash={template_hash}, "
            f"size={file_size} bytes, ttl={ttl_days} days"
        )
        return cache_path

    except OSError as e:
        logger.error(f"Filesystem error storing template in cache: {e}")
        # Clean up temp file if it exists
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        return None
    except redis.RedisError as e:
        logger.error(f"Redis error storing template metadata: {e}")
        # File was cached but metadata failed - still usable
        if cache_path and os.path.exists(cache_path):
            return cache_path
        return None
    except Exception as e:
        logger.error(f"Unexpected error storing template in cache: {e}")
        return None


def get_cached_template(template_hash: str, output_dir: str) -> Optional[str]:
    """
    Get a cached template and copy it to the output directory.

    Updates access metadata and refreshes TTL on successful retrieval.

    Args:
        template_hash: Client-provided hash identifying the template
        output_dir: Directory to copy the template to

    Returns:
        Path to the copied template file, or None if not found/failed
    """
    config = get_cache_config()

    if not config["enabled"]:
        return None

    try:
        # Check cache exists
        metadata = check_cache(template_hash)
        if not metadata:
            return None

        source_path = metadata["file_path"]

        # Generate unique filename in output dir
        output_filename = f"template_{template_hash}_{os.urandom(4).hex()}.docx"
        output_path = os.path.join(output_dir, output_filename)

        # Copy to output directory
        shutil.copy2(source_path, output_path)

        # Update access metadata and refresh TTL
        _update_access(template_hash, metadata)

        logger.info(f"Template retrieved from cache: hash={template_hash}")
        return output_path

    except OSError as e:
        logger.error(f"Filesystem error retrieving cached template: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error retrieving cached template: {e}")
        return None


def _update_access(template_hash: str, metadata: Dict[str, Any]) -> None:
    """
    Update access metadata and refresh TTL for a cached template.

    Args:
        template_hash: Client-provided hash identifying the template
        metadata: Current metadata dictionary
    """
    config = get_cache_config()
    ttl_days = config["ttl_days"]

    try:
        client = get_redis_client()
        redis_key = _get_redis_key(template_hash)

        # Update metadata
        metadata["last_accessed"] = datetime.now(timezone.utc).isoformat()
        metadata["access_count"] = metadata.get("access_count", 0) + 1

        # Refresh TTL by setting with new expiry
        ttl_seconds = ttl_days * 24 * 60 * 60
        client.setex(redis_key, ttl_seconds, json.dumps(metadata))

        logger.debug(
            f"Cache access updated for hash={template_hash}, "
            f"count={metadata['access_count']}, TTL refreshed to {ttl_days} days"
        )

    except redis.RedisError as e:
        logger.error(f"Redis error updating access metadata: {e}")
    except Exception as e:
        logger.error(f"Unexpected error updating access metadata: {e}")


def _delete_cache_entry(template_hash: str) -> bool:
    """
    Delete a cache entry (both Redis metadata and filesystem file).

    Args:
        template_hash: Client-provided hash identifying the template

    Returns:
        True if deletion was successful, False otherwise
    """
    try:
        client = get_redis_client()
        redis_key = _get_redis_key(template_hash)

        # Get file path before deleting metadata
        metadata_json = client.get(redis_key)
        if metadata_json:
            metadata = json.loads(metadata_json)
            file_path = metadata.get("file_path")

            # Delete file if it exists
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"Deleted cached file: {file_path}")

        # Delete Redis entry
        client.delete(redis_key)
        logger.debug(f"Deleted cache entry for hash: {template_hash}")
        return True

    except Exception as e:
        logger.error(f"Error deleting cache entry for hash {template_hash}: {e}")
        return False


def cleanup_expired() -> Dict[str, Any]:
    """
    Remove expired cache entries.

    Note: Redis TTL handles automatic expiry of metadata.
    This function cleans up orphaned files (files without Redis entries).

    Returns:
        Statistics about the cleanup operation
    """
    config = get_cache_config()
    cache_dir = config["cache_dir"]

    stats = {
        "orphaned_files_removed": 0,
        "bytes_freed": 0,
        "errors": 0,
    }

    if not config["enabled"]:
        return stats

    try:
        if not os.path.exists(cache_dir):
            return stats

        client = get_redis_client()

        # List all .docx files in cache directory
        for filename in os.listdir(cache_dir):
            if not filename.endswith(".docx"):
                continue

            # Extract hash from filename (remove .docx extension)
            template_hash = filename[:-5]
            redis_key = _get_redis_key(template_hash)

            # Check if Redis entry exists
            if not client.exists(redis_key):
                file_path = os.path.join(cache_dir, filename)
                try:
                    file_size = os.path.getsize(file_path)
                    os.remove(file_path)
                    stats["orphaned_files_removed"] += 1
                    stats["bytes_freed"] += file_size
                    logger.info(f"Removed orphaned cache file: {filename}")
                except OSError as e:
                    logger.error(f"Error removing orphaned file {filename}: {e}")
                    stats["errors"] += 1

        logger.info(
            f"Expired cache cleanup complete: removed {stats['orphaned_files_removed']} "
            f"orphaned files, freed {stats['bytes_freed'] / (1024*1024):.2f} MB"
        )

    except redis.RedisError as e:
        logger.error(f"Redis error during expired cleanup: {e}")
        stats["errors"] += 1
    except Exception as e:
        logger.error(f"Unexpected error during expired cleanup: {e}")
        stats["errors"] += 1

    return stats


def cleanup_by_size() -> Dict[str, Any]:
    """
    Remove oldest cache entries when total size exceeds the configured limit.

    Uses LRU (Least Recently Used) strategy based on last_accessed timestamp.

    Returns:
        Statistics about the cleanup operation
    """
    config = get_cache_config()
    cache_dir = config["cache_dir"]
    max_size_bytes = config["max_size_mb"] * 1024 * 1024

    stats = {
        "files_removed": 0,
        "bytes_freed": 0,
        "current_size_mb": 0,
        "errors": 0,
    }

    if not config["enabled"]:
        return stats

    try:
        if not os.path.exists(cache_dir):
            return stats

        client = get_redis_client()

        # Collect all cache entries with their metadata
        entries = []
        total_size = 0

        for filename in os.listdir(cache_dir):
            if not filename.endswith(".docx"):
                continue

            template_hash = filename[:-5]
            redis_key = _get_redis_key(template_hash)
            file_path = os.path.join(cache_dir, filename)

            try:
                file_size = os.path.getsize(file_path)
                total_size += file_size

                # Get metadata for sorting
                metadata_json = client.get(redis_key)
                if metadata_json:
                    metadata = json.loads(metadata_json)
                    last_accessed = metadata.get(
                        "last_accessed", "1970-01-01T00:00:00+00:00"
                    )
                else:
                    # No metadata - treat as oldest
                    last_accessed = "1970-01-01T00:00:00+00:00"

                entries.append(
                    {
                        "template_hash": template_hash,
                        "file_path": file_path,
                        "file_size": file_size,
                        "last_accessed": last_accessed,
                    }
                )
            except OSError as e:
                logger.error(f"Error reading file {filename}: {e}")
                stats["errors"] += 1

        stats["current_size_mb"] = total_size / (1024 * 1024)

        # Check if cleanup is needed
        if total_size <= max_size_bytes:
            logger.info(
                f"Cache size ({stats['current_size_mb']:.2f} MB) within limit "
                f"({config['max_size_mb']} MB), no cleanup needed"
            )
            return stats

        # Sort by last_accessed (oldest first) for LRU removal
        entries.sort(key=lambda x: x["last_accessed"])

        # Remove oldest entries until under the limit
        for entry in entries:
            if total_size <= max_size_bytes:
                break

            try:
                os.remove(entry["file_path"])
                client.delete(_get_redis_key(entry["template_hash"]))

                total_size -= entry["file_size"]
                stats["files_removed"] += 1
                stats["bytes_freed"] += entry["file_size"]

                logger.info(
                    f"Removed LRU cache entry: hash={entry['template_hash']}, "
                    f"last_accessed={entry['last_accessed']}"
                )
            except Exception as e:
                logger.error(
                    f"Error removing cache entry {entry['template_hash']}: {e}"
                )
                stats["errors"] += 1

        stats["current_size_mb"] = total_size / (1024 * 1024)
        logger.info(
            f"Size-based cleanup complete: removed {stats['files_removed']} files, "
            f"freed {stats['bytes_freed'] / (1024*1024):.2f} MB, "
            f"current size {stats['current_size_mb']:.2f} MB"
        )

    except redis.RedisError as e:
        logger.error(f"Redis error during size cleanup: {e}")
        stats["errors"] += 1
    except Exception as e:
        logger.error(f"Unexpected error during size cleanup: {e}")
        stats["errors"] += 1

    return stats


def get_cache_statistics() -> Dict[str, Any]:
    """
    Get current cache statistics.

    Returns:
        Dictionary with cache statistics
    """
    config = get_cache_config()
    cache_dir = config["cache_dir"]

    stats = {
        "enabled": config["enabled"],
        "cache_dir": cache_dir,
        "max_size_mb": config["max_size_mb"],
        "ttl_days": config["ttl_days"],
        "total_files": 0,
        "total_size_mb": 0,
        "entries": [],
    }

    if not config["enabled"] or not os.path.exists(cache_dir):
        return stats

    try:
        client = get_redis_client()
        total_size = 0

        for filename in os.listdir(cache_dir):
            if not filename.endswith(".docx"):
                continue

            template_hash = filename[:-5]
            file_path = os.path.join(cache_dir, filename)

            try:
                file_size = os.path.getsize(file_path)
                total_size += file_size
                stats["total_files"] += 1

                # Get metadata
                redis_key = _get_redis_key(template_hash)
                metadata_json = client.get(redis_key)
                if metadata_json:
                    metadata = json.loads(metadata_json)
                    stats["entries"].append(
                        {
                            "template_hash": template_hash,
                            "file_size": file_size,
                            "created_at": metadata.get("created_at"),
                            "last_accessed": metadata.get("last_accessed"),
                            "access_count": metadata.get("access_count", 0),
                        }
                    )
            except OSError:
                pass

        stats["total_size_mb"] = total_size / (1024 * 1024)

    except Exception as e:
        logger.error(f"Error getting cache statistics: {e}")

    return stats
