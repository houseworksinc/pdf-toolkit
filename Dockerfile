FROM python:3.10-slim

# Set environment variables to avoid interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# LibreOffice is now handled by the separate unoserver container
# No need to install it in the main application container

# Python setup is already handled by python:3.10-slim base image

WORKDIR /app

# Upgrade pip to latest version
RUN pip install --upgrade pip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/

CMD ["python", "app/main.py"]