#!/usr/bin/env python3
"""
Test runner script for the PDF Toolkit project.
This script runs all tests using pytest with the proper Python path configuration.
"""

import os
import sys
import subprocess


def main():
    """Run all tests with proper Python path configuration."""
    # Get the directory of this script (project root)
    project_root = os.path.dirname(os.path.abspath(__file__))

    # Set PYTHONPATH to include the project root so imports work correctly
    env = os.environ.copy()
    env["PYTHONPATH"] = project_root

    # Set required environment variables for testing
    # JWT Configuration
    env["JWT_SECRET_KEY"] = env.get("JWT_SECRET_KEY", "test-secret-key")
    env["JWT_ACCESS_TOKEN_EXPIRES"] = env.get(
        "JWT_ACCESS_TOKEN_EXPIRES", "3600"
    )

    # Database Configuration
    env["POSTGRES_USER"] = env.get("POSTGRES_USER", "test")
    env["POSTGRES_PASSWORD"] = env.get("POSTGRES_PASSWORD", "test")
    env["POSTGRES_DB"] = env.get("POSTGRES_DB", "test")

    # Admin User Configuration
    env["MASTER_USERNAME"] = env.get("MASTER_USERNAME", "testadmin")
    env["MASTER_PASSWORD"] = env.get("MASTER_PASSWORD", "testpassword")

    # AWS Configuration
    env["AWS_S3_BUCKET_NAME"] = env.get("AWS_S3_BUCKET_NAME", "test-bucket")
    env["AWS_REGION"] = env.get("AWS_REGION", "us-east-1")

    # Celery Configuration
    env["CELERY_BROKER_URL"] = env.get(
        "CELERY_BROKER_URL", "redis://localhost:6379/0"
    )
    env["CELERY_RESULT_BACKEND"] = env.get(
        "CELERY_RESULT_BACKEND", "redis://localhost:6379/0"
    )

    # Environment
    env["ENV"] = env.get("ENV", "local")

    # Run pytest with verbose output
    cmd = [sys.executable, "-m", "pytest", "app/tests/", "-v"]

    print("Running tests...")
    print(f"Command: {' '.join(cmd)}")
    print(f"PYTHONPATH: {project_root}")
    print("-" * 50)

    # Run the tests
    result = subprocess.run(cmd, cwd=project_root, env=env)

    # Exit with the same code as pytest
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
