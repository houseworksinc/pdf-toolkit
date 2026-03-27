import datetime
import decimal
import json
import logging
import uuid


def _json_default(obj):
    """
    Serializer for non-JSON-native types.
    - datetime/date/time -> ISO 8601 string
    - Decimal -> float
    - UUID -> string
    - set -> list
    - bytes -> UTF-8 string (replace invalid)
    - Fallback -> str(obj)
    """
    if isinstance(obj, (datetime.datetime, datetime.date, datetime.time)):
        return obj.isoformat()
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, set):
        return list(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    # stringify the object
    return str(obj)


class JsonFormatter(logging.Formatter):
    def __init__(self, timestamp_format: str = "%Y-%m-%d %H:%M:%S.%f"):
        super().__init__()
        self.timestamp_format = timestamp_format

    def format(
        self,
        record,
    ):
        log_data = {
            "timestamp": datetime.datetime.fromtimestamp(
                record.created
            ).strftime(self.timestamp_format)[:-3],
            "level": record.levelname,
            "name": record.name,
            "path": record.pathname,
            "module": record.module,
            "function": record.funcName,
            "message": record.getMessage(),
            "exception": "",
            # "extra": {},
        }

        # Add exception info if present for ERROR
        if record.exc_info:
            log_data["exception"] = "{}".format(
                self.formatException(record.exc_info)
            )

        # Add extra fields if present
        # if hasattr(record, "extra"):
        #     log_data.update(record.extra)

        return json.dumps(log_data, default=_json_default)
