from flask import Flask
import os
import logging
from logging.handlers import RotatingFileHandler
from app.logger_formatter import JsonFormatter

app = Flask(__name__)

# JWT Configuration
jwt_secret = os.environ.get("JWT_SECRET_KEY")
if not jwt_secret:
    raise ValueError("JWT_SECRET_KEY environment variable is required")
app.config["JWT_SECRET_KEY"] = jwt_secret
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = int(
    os.environ.get("JWT_ACCESS_TOKEN_EXPIRES", 86400)
)  # Default 24 hours

# SQLAlchemy Configuration
# Build default DATABASE_URL from individual env vars if DATABASE_URL not provided
postgres_user = os.environ.get("POSTGRES_USER")
postgres_password = os.environ.get("POSTGRES_PASSWORD")
postgres_db = os.environ.get("POSTGRES_DB")
postgres_host = os.environ.get(
    "POSTGRES_HOST", "postgres"
)  # Default to 'postgres' for Docker

if not all([postgres_user, postgres_password, postgres_db]):
    raise ValueError(
        "POSTGRES_USER, POSTGRES_PASSWORD, and POSTGRES_DB environment variables are required"
    )

default_db_url = "postgresql://{user}:{password}@{host}:5432/{db}".format(
    user=postgres_user,
    password=postgres_password,
    host=postgres_host,
    db=postgres_db,
)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", default_db_url
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ECHO"] = (
    os.environ.get("SQLALCHEMY_ECHO", "False").lower() == "true"
)

# Limits Configuration
app.config["MAX_DOWNLOADS_PER_JOB"] = int(
    os.environ.get("MAX_DOWNLOADS_PER_JOB", 600)
)
app.config["MAX_DOWNLOAD_SIZE_MB"] = int(
    os.environ.get("MAX_DOWNLOAD_SIZE_MB", 1024)
)
app.config["MAX_QUEUED_REQUESTS"] = int(
    os.environ.get("MAX_QUEUED_REQUESTS", 300)
)
app.config["CELERY_WORKER_CONCURRENCY"] = int(
    os.environ.get("CELERY_WORKER_CONCURRENCY", 2)
)

# ===== UnoServer Configuration =====
app.config["UNOSERVER_HOST"] = os.environ.get("UNOSERVER_HOST", "unoserver")
app.config["UNOSERVER_PORT"] = int(os.environ.get("UNOSERVER_PORT", "2003"))
app.config["UNO_SERVER_TIMEOUT"] = int(os.environ.get("UNO_SERVER_TIMEOUT", "60"))

# ===== Template Cache Configuration =====
app.config["TEMPLATE_CACHE_ENABLED"] = (
    os.environ.get("TEMPLATE_CACHE_ENABLED", "true").lower() == "true"
)
app.config["TEMPLATE_CACHE_DIR"] = os.environ.get(
    "TEMPLATE_CACHE_DIR", "/app/template_cache"
)
app.config["TEMPLATE_CACHE_MAX_SIZE_MB"] = int(
    os.environ.get("TEMPLATE_CACHE_MAX_SIZE_MB", 500)
)
app.config["TEMPLATE_CACHE_TTL_DAYS"] = int(
    os.environ.get("TEMPLATE_CACHE_TTL_DAYS", 7)
)

# ===== Logging Configuration =====
# Configure logging for the entire application
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Create logs directory if it doesn't exist
logs_dir = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "logs"
)
os.makedirs(logs_dir, exist_ok=True)

# Create file handler with JSON formatter
file_handler = RotatingFileHandler(
    os.path.join(logs_dir, "app.log"),
    maxBytes=10485760,  # 10MB
    backupCount=10,
)
file_handler.setFormatter(JsonFormatter())

# Configure root logger
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format=LOG_FORMAT,
    datefmt=LOG_DATE_FORMAT,
    handlers=[
        # Console handler - prints to stdout
        logging.StreamHandler(),
        # File handler - writes to rotating log file with JSON formatting
        file_handler,
    ],
)

# Set Flask app logger
app.logger.setLevel(getattr(logging, LOG_LEVEL))

# Reduce noise from third-party libraries
logging.getLogger("werkzeug").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# Log UnoServer configuration
app.logger.info(
    f"PDF Conversion: UnoServer configured at "
    f"{app.config['UNOSERVER_HOST']}:{app.config['UNOSERVER_PORT']}"
)

# Create template cache directory if enabled
if app.config["TEMPLATE_CACHE_ENABLED"]:
    cache_dir = app.config["TEMPLATE_CACHE_DIR"]
    try:
        os.makedirs(cache_dir, exist_ok=True)
        app.logger.info(f"Template cache directory: {cache_dir}")
    except Exception as e:
        app.logger.error(f"Failed to create cache directory: {e}")

# Initialize SQLAlchemy
from app.models import db

db.init_app(app)

# Register error handlers
from app.error_handlers import register_error_handlers

register_error_handlers(app)
