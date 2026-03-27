"""Helper functions for task priority management"""

# Priority level constants
PRIORITY_HIGH = 0
PRIORITY_MEDIUM = 1
PRIORITY_LOW = 2

# Queue name mapping
PRIORITY_QUEUE_MAP = {
    PRIORITY_HIGH: "high_priority",
    PRIORITY_MEDIUM: "medium_priority",
    PRIORITY_LOW: "low_priority",
}


def validate_priority(priority):
    """
    Validate priority parameter.

    Args:
        priority: Priority value (should be 0, 1, or 2)

    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    if priority is None:
        return True, None

    if not isinstance(priority, int):
        return False, "priority must be an integer (0=High, 1=Medium, 2=Low)"

    if priority not in [PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW]:
        return False, f"priority must be 0 (High), 1 (Medium), or 2 (Low), got {priority}"

    return True, None


def get_queue_for_priority(priority):
    """Get queue name for a given priority level."""
    return PRIORITY_QUEUE_MAP.get(priority, "medium_priority")


def invoke_task_with_priority(task_function, priority, **task_kwargs):
    """
    Invoke a Celery task with optional priority override.

    Args:
        task_function: Celery task object
        priority: Priority level (0, 1, 2) or None for default routing
        **task_kwargs: Task arguments

    Returns:
        AsyncResult: Celery task result
    """
    if priority is not None:
        queue_name = get_queue_for_priority(priority)
        return task_function.apply_async(kwargs=task_kwargs, queue=queue_name)
    else:
        return task_function.delay(**task_kwargs)
