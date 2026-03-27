"""Error handlers for database and API exceptions"""

from flask import jsonify
from sqlalchemy.exc import (
    IntegrityError,
    DataError,
    OperationalError,
    DatabaseError,
)
from werkzeug.exceptions import HTTPException
import logging

logger = logging.getLogger(__name__)


def format_db_error(error):
    """
    Format database errors into user-friendly messages.

    Args:
        error: SQLAlchemy exception

    Returns:
        tuple: (error_message, status_code)
    """
    error_str = str(error.orig) if hasattr(error, "orig") else str(error)

    # Handle IntegrityError (unique constraints, foreign key violations, not null, etc.)
    if isinstance(error, IntegrityError):
        if (
            "null value in column" in error_str
            or "NOT NULL constraint" in error_str
        ):
            # Extract column name if possible
            if "client_job_id" in error_str:
                return "client_job_id is required and cannot be empty", 400
            else:
                return "Required field is missing", 400

        elif "violates foreign key constraint" in error_str:
            return "Referenced record does not exist", 400

        else:
            return "Database constraint violation", 400

    # Handle DataError (invalid data type, value too long, etc.)
    elif isinstance(error, DataError):
        if "value too long" in error_str:
            return "One or more fields exceed the maximum allowed length", 400
        elif "invalid input syntax" in error_str:
            return "Invalid data format provided", 400
        else:
            return "Invalid data provided", 400

    # Handle OperationalError (database connection issues)
    elif isinstance(error, OperationalError):
        logger.error(f"Database operational error: {error_str}")
        return "Database connection error. Please try again later", 503

    # Handle generic DatabaseError
    elif isinstance(error, DatabaseError):
        logger.error(f"Database error: {error_str}")
        return (
            "Database error occurred. Please contact support if this persists",
            500,
        )

    # Unknown error
    else:
        logger.error(f"Unexpected database error: {error_str}")
        return "An unexpected error occurred", 500


def register_error_handlers(app):
    """
    Register error handlers for the Flask application.

    Args:
        app: Flask application instance
    """

    @app.errorhandler(IntegrityError)
    def handle_integrity_error(error):
        """Handle SQLAlchemy IntegrityError"""
        from app.models import db

        db.session.rollback()

        message, status_code = format_db_error(error)
        logger.warning(f"IntegrityError: {str(error)}")

        return jsonify(
            {"error": message, "status_code": status_code}
        ), status_code

    @app.errorhandler(DataError)
    def handle_data_error(error):
        """Handle SQLAlchemy DataError"""
        from app.models import db

        db.session.rollback()

        message, status_code = format_db_error(error)
        logger.warning(f"DataError: {str(error)}")

        return jsonify(
            {"error": message, "status_code": status_code}
        ), status_code

    @app.errorhandler(OperationalError)
    def handle_operational_error(error):
        """Handle SQLAlchemy OperationalError"""
        from app.models import db

        db.session.rollback()

        message, status_code = format_db_error(error)
        logger.error(f"OperationalError: {str(error)}")

        return jsonify(
            {"error": message, "status_code": status_code}
        ), status_code

    @app.errorhandler(DatabaseError)
    def handle_database_error(error):
        """Handle generic SQLAlchemy DatabaseError"""
        from app.models import db

        db.session.rollback()

        message, status_code = format_db_error(error)
        logger.error(f"DatabaseError: {str(error)}")

        return jsonify(
            {"error": message, "status_code": status_code}
        ), status_code

    @app.errorhandler(HTTPException)
    def handle_http_exception(error):
        """Handle Werkzeug HTTP exceptions"""
        return jsonify(
            {"error": error.description, "status_code": error.code}
        ), error.code

    @app.errorhandler(Exception)
    def handle_generic_error(error):
        """Handle any unhandled exceptions"""
        logger.error(f"Unhandled exception: {str(error)}", exc_info=True)

        return jsonify(
            {"error": "An unexpected error occurred", "status_code": 500}
        ), 500
