"""Main Celery worker configuration and task registration"""

from celery import Celery
from kombu import Queue, Exchange
import os
import boto3

# Initialize Celery with broker and backend configuration
celery_broker = os.environ.get("CELERY_BROKER_URL")
celery_backend = os.environ.get("CELERY_RESULT_BACKEND")

if not celery_broker:
    raise ValueError("CELERY_BROKER_URL environment variable is required")
if not celery_backend:
    raise ValueError("CELERY_RESULT_BACKEND environment variable is required")

celery = Celery("pdf_toolkit", broker=celery_broker, backend=celery_backend)

# Configure Celery
celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# Configure task routing and queue priorities
celery.conf.task_routes = {
    # High priority tasks (0)
    "generate_pdf_task": {"queue": "high_priority"},
    "generate_pdf_dynamic_task": {"queue": "high_priority"},
    # Medium priority tasks (1)
    "split_pdf_task": {"queue": "medium_priority"},
    "merge_pdfs_task": {"queue": "medium_priority"},
    "create_zip_task": {"queue": "medium_priority"},
    # Low priority tasks (2)
    "process_and_merge_task": {"queue": "low_priority"},
    "process_and_zip_task": {"queue": "low_priority"},
    "cleanup_template_cache_task": {"queue": "low_priority"},
}

# Define all queues
celery.conf.task_queues = (
    Queue("high_priority", Exchange("high_priority"), routing_key="high_priority"),
    Queue("medium_priority", Exchange("medium_priority"), routing_key="medium_priority"),
    Queue("low_priority", Exchange("low_priority"), routing_key="low_priority"),
)

# Set default queue for tasks without explicit routing
celery.conf.task_default_queue = "medium_priority"
celery.conf.task_default_exchange = "medium_priority"
celery.conf.task_default_routing_key = "medium_priority"

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

# Import and register all task workers
from app.workers.generate_pdf_worker import register_generate_pdf_task
from app.workers.split_pdf_worker import register_split_pdf_task
from app.workers.generate_pdf_dynamic_worker import (
    register_generate_pdf_dynamic_task,
)
from app.workers.merge_pdfs_worker import register_merge_pdfs_task
from app.workers.create_zip_worker import register_create_zip_task

# Register tasks with Celery
generate_pdf_task = register_generate_pdf_task(celery, s3_client, s3_bucket)
split_pdf_task = register_split_pdf_task(celery)
generate_pdf_dynamic_task = register_generate_pdf_dynamic_task(
    celery, s3_client, s3_bucket
)
merge_pdfs_task = register_merge_pdfs_task(celery, s3_client, s3_bucket)
create_zip_task = register_create_zip_task(celery, s3_client, s3_bucket)

# Import process_and_merge_worker to register the task
from app.workers import process_and_merge_worker

# Import process_and_zip_worker to register the task
from app.workers import process_and_zip_worker

# Import cleanup_template_cache_worker to register the task
from app.workers import cleanup_template_cache_worker

# Configure Celery Beat schedule for periodic tasks
celery.conf.beat_schedule = {
    "cleanup-template-cache": {
        "task": "cleanup_template_cache_task",
        "schedule": 3600.0,  # Run every 1 hour (in seconds)
    },
}
