"""Celery worker for template cache cleanup"""

import logging

from app.workers.celery_worker import celery
from app.services.template_cache import (
    cleanup_expired,
    cleanup_by_size,
    get_cache_statistics,
)

logger = logging.getLogger(__name__)


@celery.task(name="cleanup_template_cache_task")
def cleanup_template_cache_task():
    """
    Periodic task to cleanup template cache.

    Runs:
    1. Expired/orphaned file cleanup (files without Redis entries)
    2. Size-based cleanup (LRU removal when exceeding max size)
    3. Logs statistics after cleanup

    This task is scheduled to run hourly via Celery Beat.
    """
    logger.info("Starting template cache cleanup task")

    try:
        # Step 1: Clean up orphaned files (Redis entries expired but files remain)
        expired_stats = cleanup_expired()
        logger.info(
            f"Expired cleanup: removed {expired_stats['orphaned_files_removed']} "
            f"orphaned files, freed {expired_stats['bytes_freed'] / (1024*1024):.2f} MB"
        )

        # Step 2: Size-based cleanup (LRU when exceeding limit)
        size_stats = cleanup_by_size()
        logger.info(
            f"Size cleanup: removed {size_stats['files_removed']} files, "
            f"freed {size_stats['bytes_freed'] / (1024*1024):.2f} MB, "
            f"current size {size_stats['current_size_mb']:.2f} MB"
        )

        # Step 3: Get and log current statistics
        stats = get_cache_statistics()
        logger.info(
            f"Cache statistics: {stats['total_files']} files, "
            f"{stats['total_size_mb']:.2f} MB / {stats['max_size_mb']} MB limit"
        )

        return {
            "success": True,
            "expired_cleanup": expired_stats,
            "size_cleanup": size_stats,
            "final_stats": {
                "total_files": stats["total_files"],
                "total_size_mb": stats["total_size_mb"],
                "max_size_mb": stats["max_size_mb"],
            },
        }

    except Exception as e:
        logger.error(f"Template cache cleanup failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }

