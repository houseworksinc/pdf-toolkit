import os
import boto3
import requests
import logging
from typing import Dict, Any, Optional
from botocore.exceptions import NoCredentialsError, ClientError

logger = logging.getLogger(__name__)

# S3 configuration
s3_bucket = os.environ.get("AWS_S3_BUCKET_NAME")
aws_region = os.environ.get("AWS_REGION")
# Presigned URL expiry in seconds (default: 1 hour, max: 7 days = 604800 seconds)
presigned_url_expiry = int(os.environ.get("AWS_PRESIGNED_URL_EXPIRY", 3600))

if not s3_bucket:
    raise ValueError("AWS_S3_BUCKET_NAME environment variable is required")
if not aws_region:
    raise ValueError("AWS_REGION environment variable is required")

# Initialize S3 client
s3_client = boto3.client("s3", region_name=aws_region)


def generate_s3_presigned_url(
    s3_key: str,
    bucket: str = None,
    expiry: int = None,
    content_type: str = "application/pdf",
) -> str:
    """
    Generate a presigned URL for downloading a file from S3.

    Args:
        s3_key: S3 key (path) for the file
        bucket: S3 bucket name (default: uses AWS_S3_BUCKET_NAME from env)
        expiry: URL expiry time in seconds (default: uses AWS_PRESIGNED_URL_EXPIRY from env)
        content_type: MIME type for the response (default: 'application/pdf')

    Returns:
        Presigned URL string
    """
    bucket = bucket or s3_bucket
    expiry = expiry or presigned_url_expiry

    presigned_url = s3_client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": bucket,
            "Key": s3_key,
            "ResponseContentDisposition": "inline",
            "ResponseContentType": content_type,
        },
        ExpiresIn=expiry,
    )
    return presigned_url


def upload_to_s3(
    file_path: str, s3_key: str, generate_presigned_url: bool = True
) -> Dict[str, Any]:
    """
    Upload a file to S3 bucket.

    Args:
        file_path: Local path to the file to upload
        s3_key: S3 key (path) for the uploaded file
        generate_presigned_url: Whether to generate a presigned download URL (default: True)

    Returns:
        Dictionary containing upload result:
        {
            'success': bool,
            's3_key': str,
            'download_url': str (if generate_presigned_url=True),
            'file_size': int,
            'error': str (if failed)
        }
    """
    result = {
        "success": False,
        "s3_key": None,
        "download_url": None,
        "file_size": 0,
        "error": None,
    }

    if not os.path.exists(file_path):
        error_msg = f"File not found: {file_path}"
        logger.error(error_msg)
        result["error"] = error_msg
        return result

    if not s3_bucket:
        error_msg = "AWS_S3_BUCKET_NAME environment variable not set"
        logger.error(error_msg)
        result["error"] = error_msg
        return result

    try:
        # Get file size
        file_size = os.path.getsize(file_path)

        # Upload to S3
        logger.info(f"Uploading {file_path} to s3://{s3_bucket}/{s3_key}")
        s3_client.upload_file(file_path, s3_bucket, s3_key)

        result["success"] = True
        result["s3_key"] = s3_key
        result["file_size"] = file_size

        # Generate presigned URL if requested
        if generate_presigned_url:
            result["download_url"] = generate_s3_presigned_url(s3_key)
            logger.info(
                f"Successfully uploaded to S3 with presigned URL (expires in {presigned_url_expiry}s)"
            )
        else:
            logger.info(f"Successfully uploaded to S3: {s3_key}")

    except NoCredentialsError:
        error_msg = "AWS credentials not found"
        logger.error(error_msg)
        result["error"] = error_msg
    except ClientError as e:
        error_msg = f"AWS S3 error: {str(e)}"
        logger.error(error_msg)
        result["error"] = error_msg
    except Exception as e:
        error_msg = f"Unexpected error uploading to S3: {str(e)}"
        logger.error(error_msg)
        result["error"] = error_msg

    return result


def upload_to_presigned_url(
    file_path: str, presigned_url: str
) -> Dict[str, Any]:
    """
    Upload a file to a presigned URL (e.g., AWS S3 presigned PUT URL).

    Args:
        file_path: Local path to the file to upload
        presigned_url: Presigned URL to upload to

    Returns:
        Dictionary containing upload result:
        {
            'success': bool,
            'upload_url': str,
            'file_size': int,
            'status_code': int,
            'error': str (if failed)
        }
    """
    result = {
        "success": False,
        "upload_url": presigned_url,
        "file_size": 0,
        "status_code": None,
        "error": None,
    }

    if not os.path.exists(file_path):
        error_msg = f"File not found: {file_path}"
        logger.error(error_msg)
        result["error"] = error_msg
        return result

    try:
        # Get file size
        file_size = os.path.getsize(file_path)

        # Read file content
        with open(file_path, "rb") as f:
            file_content = f.read()

        # Upload to presigned URL
        logger.info(
            f"Uploading {file_path} ({file_size} bytes) to presigned URL"
        )

        # Determine content type based on file extension
        content_type = (
            "application/pdf"
            if file_path.endswith(".pdf")
            else "application/octet-stream"
        )

        response = requests.put(
            presigned_url,
            data=file_content,
            headers={"Content-Type": content_type},
            timeout=60,
        )

        result["status_code"] = response.status_code
        result["file_size"] = file_size

        if 200 <= response.status_code < 300:
            result["success"] = True
            logger.info(
                f"Successfully uploaded to presigned URL (status: {response.status_code})"
            )
        else:
            error_msg = f"Upload failed with status {response.status_code}: {response.text[:200]}"
            logger.error(error_msg)
            result["error"] = error_msg

    except requests.exceptions.Timeout:
        error_msg = "Upload request timed out"
        logger.error(error_msg)
        result["error"] = error_msg
    except requests.exceptions.RequestException as e:
        error_msg = f"HTTP request error: {str(e)}"
        logger.error(error_msg)
        result["error"] = error_msg
    except Exception as e:
        error_msg = f"Unexpected error uploading to presigned URL: {str(e)}"
        logger.error(error_msg)
        result["error"] = error_msg

    return result


def upload_split_file(
    file_path: str,
    output_filename: str,
    job_id: str,
    split_index: int,
    file_upload_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Upload a split PDF file using either S3 or presigned URL based on configuration.

    This is a convenience function that chooses the appropriate upload method.

    Args:
        file_path: Local path to the file to upload
        output_filename: Name of the file (used for S3 key)
        job_id: Job UUID (used for S3 key organization)
        split_index: Index of the split (used for S3 key naming)
        file_upload_url: Optional presigned URL to upload to. If not provided, uploads to S3.

    Returns:
        Dictionary containing upload result:
        {
            'success': bool,
            's3_key': str (if S3 upload),
            'download_url': str (if available),
            'file_size': int,
            'upload_method': 's3' | 'presigned_url',
            'error': str (if failed)
        }
    """
    if file_upload_url:
        # Upload to presigned URL
        logger.info(f"Uploading {output_filename} to presigned URL")
        upload_result = upload_to_presigned_url(file_path, file_upload_url)

        return {
            "success": upload_result["success"],
            "s3_key": None,
            "download_url": file_upload_url
            if upload_result["success"]
            else None,
            "file_size": upload_result["file_size"],
            "upload_method": "presigned_url",
            "error": upload_result.get("error"),
        }
    else:
        # Upload to S3 - use output_filename if provided, otherwise job_id with index
        if output_filename:
            # Ensure .pdf extension
            if not output_filename.lower().endswith('.pdf'):
                s3_key = f"pdfs/split/{output_filename}.pdf"
            else:
                s3_key = f"pdfs/split/{output_filename}"
        else:
            s3_key = f"pdfs/split/{job_id}_{split_index:04d}.pdf"
        logger.info(f"Uploading split file to S3: {s3_key}")
        upload_result = upload_to_s3(
            file_path, s3_key, generate_presigned_url=True
        )

        return {
            "success": upload_result["success"],
            "s3_key": upload_result["s3_key"],
            "download_url": upload_result.get("download_url"),
            "file_size": upload_result["file_size"],
            "upload_method": "s3",
            "error": upload_result.get("error"),
        }
