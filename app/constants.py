"""
Application Constants

This module defines all constants and enums used across the application.
"""


class Status:
    """Status constants used across application (database, API, webhooks)"""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL_COMPLETED = "partial_completed"
    CANCELLED = "cancelled"


class JobType:
    """Job type constants"""

    GENERATE = "generate"
    MERGE = "merge"
    SPLIT = "split"
    ZIP = "zip"
    PARSE = "parse"
    PROCESS_AND_MERGE = "process_and_merge"
    PROCESS_AND_ZIP = "process_and_zip"
    CONVERT = "convert"


class CeleryState:
    """Celery task state constants"""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
