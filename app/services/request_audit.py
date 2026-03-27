import os
import json
import boto3
import logging
from typing import Dict, Any, Optional
from botocore.exceptions import NoCredentialsError, ClientError

logger = logging.getLogger(__name__)

# S3 configuration
s3_bucket = os.environ.get("AWS_S3_BUCKET_NAME")
aws_region = os.environ.get("AWS_REGION")

if not s3_bucket:
    raise ValueError("AWS_S3_BUCKET_NAME environment variable is required")
if not aws_region:
    raise ValueError("AWS_REGION environment variable is required")

# Initialize S3 client
s3_client = boto3.client("s3", region_name=aws_region)


def store_audit_data(
    job_id: str, request_data: Dict[str, Any]
) -> Optional[str]:
    """
    Store audit data (original API request) to S3 for compliance purposes.

    Files are stored with the path: request_audit/{job_id}.json
    Set up S3 lifecycle policy to auto-delete after 90 days.

    Args:
        job_id: Unique job identifier (UUID)
        request_data: Original API request data to store

    Returns:
        S3 key if successful, None if failed
    """
    s3_key = f"request_audit/{job_id}.json"

    try:
        # Convert to JSON with pretty printing for readability
        json_content = json.dumps(request_data, indent=2, default=str)

        # Upload to S3
        logger.info(f"Storing audit data to s3://{s3_bucket}/{s3_key}")
        s3_client.put_object(
            Bucket=s3_bucket,
            Key=s3_key,
            Body=json_content.encode("utf-8"),
            ContentType="application/json",
            # Optional: Add metadata for tracking
            Metadata={"job_id": str(job_id), "audit_type": "api_request"},
        )

        logger.info(f"Successfully stored audit data: {s3_key}")
        return s3_key

    except NoCredentialsError:
        logger.error("AWS credentials not found - cannot store audit data")
        return None
    except ClientError as e:
        logger.error(f"AWS S3 error storing audit data: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error storing audit data: {str(e)}")
        return None


def get_audit_data(job_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve audit data from S3 for a specific job.

    This is useful for compliance reviews or debugging.

    Args:
        job_id: Unique job identifier (UUID)

    Returns:
        Dictionary containing the original request data, or None if not found/error
    """
    s3_key = f"request_audit/{job_id}.json"

    try:
        logger.info(f"Retrieving audit data from s3://{s3_bucket}/{s3_key}")
        response = s3_client.get_object(Bucket=s3_bucket, Key=s3_key)
        json_content = response["Body"].read().decode("utf-8")
        audit_data = json.loads(json_content)

        logger.info(f"Successfully retrieved audit data: {s3_key}")
        return audit_data

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        if error_code == "NoSuchKey":
            logger.warning(f"Audit data not found: {s3_key}")
        else:
            logger.error(f"AWS S3 error retrieving audit data: {str(e)}")
        return None
    except NoCredentialsError:
        logger.error("AWS credentials not found - cannot retrieve audit data")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in audit data: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error retrieving audit data: {str(e)}")
        return None
