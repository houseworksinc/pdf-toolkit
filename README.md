# HouseWorks PDF Toolkit

<div align="center">

**Enterprise-grade PDF generation and manipulation microservice**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/flask-2.x-green.svg)](https://flask.palletsprojects.com/)
[![Celery](https://img.shields.io/badge/celery-5.x-brightgreen.svg)](https://docs.celeryq.dev/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

</div>

---

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Documentation](#documentation)
- [API Endpoints](#api-endpoints)
- [Environment Setup](#environment-setup)
- [Deployment](#deployment)
- [Testing](#testing)
- [Contributing](#contributing)
- [License](#license)

---

## 🎯 Overview

HouseWorks PDF Toolkit is a production-ready microservice for generating, manipulating, and distributing PDF documents at scale. Built with Flask, Celery, and PyMuPDF, it provides a RESTful API for:

- **Dynamic PDF Generation**: Create PDFs from DOCX templates with rich data injection
- **PDF Merging**: Merge multiple PDFs and images into a single PDF document
- **ZIP Archive Creation**: Create ZIP archives from any file types
- **PDF Splitting**: Split large PDFs by page numbers or logical labels
- **Asynchronous Processing**: Queue-based job processing with Celery
- **Webhook Notifications**: Real-time status updates with HMAC-secured webhooks
- **Cloud Storage**: Automatic S3 upload with presigned URLs
- **Enterprise Auth**: JWT-based authentication with user management

### Use Cases

- 📄 Generate personalized documents (invoices, reports, certificates)
- 🔗 Merge multiple PDFs and images into consolidated documents
- 📦 Create ZIP archives for document packages and file delivery
- ✂️ Split contracts or legal documents by sections
- 📊 Create dynamic reports with tables, charts, and formatting
- 🔄 Batch process documents asynchronously
- 🔔 Get real-time updates via webhooks
- ☁️ Store and distribute PDFs via cloud storage

---

## ✨ Features

### PDF Generation

- **Static Templates**: Simple placeholder replacement in DOCX templates
- **Dynamic Content**: Rich text formatting with paragraphs, lists, tables, headings
- **Image Support**: Embed images from URLs with automatic download
- **Custom Styling**: Apply Word styles programmatically
- **UnoServer Integration**: High-fidelity DOCX to PDF conversion via dedicated LibreOffice UnoServer container

### PDF Merging

- **Multi-Format Support**: Merge PDFs and images (PNG, JPG, GIF, BMP, TIFF, SVG)
- **Direct Merge**: Native PDF merging for optimal quality and performance
- **Image Conversion**: Automatic image-to-PDF conversion via PyMuPDF
- **Custom Output**: Configurable output filename
- **Flexible Upload**: Upload to S3 or custom presigned URLs
- **Webhook Notifications**: Real-time status updates on completion

### ZIP Archive Creation

- **Universal Support**: Accept any file type (PDFs, images, documents, videos, audio, etc.)
- **Flat Structure**: All files stored at ZIP root level for easy access
- **Compressed Archives**: ZIP_DEFLATED compression for optimal file size
- **Custom Naming**: Configurable archive filename
- **Flexible Upload**: Upload to S3 or custom presigned URLs
- **Webhook Notifications**: Real-time status updates on completion

### PDF Splitting

- **Physical Pages**: Split by 1-indexed page numbers
- **Logical Labels**: Split by page labels (i, ii, iii, 1, 2, 3, etc.)
- **Batch Processing**: Process multiple splits in a single job
- **Flexible Upload**: Upload to S3 or custom presigned URLs
- **Progress Tracking**: Real-time progress via webhooks

### System Features

- **JWT Authentication**: Secure token-based auth with refresh
- **Webhook System**: HMAC-SHA256 signed notifications
- **Job Queuing**: Redis-backed Celery for async processing
- **Database Logging**: SQLite with comprehensive job tracking
- **Error Handling**: Graceful failures with detailed error messages
- **Docker Support**: Containerized deployment with docker-compose

---

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose (recommended)
- OR: Python 3.10+, Redis, UnoServer (for local development)
- AWS S3 bucket (for file storage)

### Installation (Docker)

```bash
# 1. Clone the repository
git clone <repository-url>
cd pdf-toolkit

# 2. Create .env file
cp .env.example .env
# Edit .env with your configuration

# 3. Start services
docker-compose up -d

# 4. Check status
docker-compose ps

# 5. View logs
docker-compose logs -f
```

### First API Call

```bash
# 1. Login as master user to get JWT token
MASTER_TOKEN=$(curl -X POST http://localhost:5001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "your_master_password"
  }' | jq -r '.token')

# 2. Register a new user (requires master user authentication)
curl -X POST http://localhost:5001/api/v1/auth/register \
  -H "Authorization: Bearer $MASTER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "demo",
    "password": "demo123"
  }'

# 3. Login as the new user to get their JWT token
TOKEN=$(curl -X POST http://localhost:5001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "demo",
    "password": "demo123"
  }' | jq -r '.token')

# 4. Generate a PDF
curl -X POST http://localhost:5001/api/v1/generate-pdf \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "client_job_id": "test-001",
    "template_url": "https://example.com/template.docx",
    "data": {
      "name": "John Doe",
      "date": "2025-10-03"
    }
  }'
```

---

## 🏗️ Architecture

```
┌─────────────────┐
│   Client App    │
└────────┬────────┘
         │ HTTPS + JWT
         ▼
┌─────────────────────────────────┐
│      Flask API (Port 5001)      │
│  ┌──────────────────────────┐   │
│  │  Blueprints:             │   │
│  │  • /api/v1/auth          │   │
│  │  • /api/v1/generate-pdf  │   │
│  │  • /api/v1/merge-pdfs    │   │
│  │  • /api/v1/create-zip    │   │
│  │  • /api/v1/split-pdf     │   │
│  │  • /api/v1/webhook       │   │
│  │  • /api/v1/logs          │   │
│  └──────────────────────────┘   │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│   Celery Workers (async)        │
│  ┌──────────────────────────┐   │
│  │  Tasks:                  │   │
│  │  • generate_pdf_task     │   │
│  │  • generate_pdf_dynamic  │   │
│  │  • split_pdf_task        │   │
│  │  • merge_pdfs_task       │   │
│  │  • create_zip_task       │   │
│  └──────────────────────────┘   │
└────────┬────────────────────────┘
         │
    ┌────┴────┬──────────┬──────────┐
    ▼         ▼          ▼          ▼
┌────────┐ ┌─────┐  ┌──────┐  ┌─────────┐
│ Redis  │ │ S3  │  │SQLite│  │Webhook  │
│ Queue  │ │Store│  │  DB  │  │Endpoint │
└────────┘ └─────┘  └──────┘  └─────────┘
```

**Key Components:**

- **Flask API**: RESTful endpoints with JWT auth
- **Celery Workers**: Async task processing
- **Redis**: Message broker for Celery
- **PostgreSQL**: Job logging and user management
- **S3**: Cloud storage for generated PDFs
- **UnoServer**: Dedicated LibreOffice container for document conversion via UNO API

For detailed architecture, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## 📚 Documentation

| Document                             | Description                         |
| ------------------------------------ | ----------------------------------- |
| [API Reference](docs/API.md)         | Complete API endpoint documentation |
| [Webhooks Guide](docs/WEBHOOKS.md)   | Webhook setup and authentication    |
| [Architecture](docs/ARCHITECTURE.md) | System design and components        |
| [Deployment](docs/DEPLOYMENT.md)     | Production deployment guide         |
| [Development](docs/DEVELOPMENT.md)   | Developer setup and guidelines      |
| [Testing](docs/TESTING.md)           | Testing guide and coverage          |

---

## 🔌 API Endpoints

### Authentication

| Method | Endpoint                    | Description                          | Auth Required |
| ------ | --------------------------- | ------------------------------------ | ------------- |
| POST   | `/api/v1/auth/register`     | Register new user (master user only) | Yes (Master)  |
| POST   | `/api/v1/auth/login`        | Login and get JWT token              | No            |
| GET    | `/api/v1/auth/authenticate` | Verify JWT token                     | Yes           |

### PDF Generation

| Method | Endpoint                       | Description                              |
| ------ | ------------------------------ | ---------------------------------------- |
| POST   | `/api/v1/generate-pdf`         | Generate PDF (static)                    |
| POST   | `/api/v1/generate-pdf/dynamic` | Generate PDF (dynamic)                   |
| GET    | `/api/v1/generate-pdf/status`  | Check generation status (static/dynamic) |

### PDF Merging

| Method | Endpoint                    | Description            |
| ------ | --------------------------- | ---------------------- |
| POST   | `/api/v1/merge-pdfs`        | Merge PDFs and images  |
| GET    | `/api/v1/merge-pdfs/status` | Check merge job status |

### ZIP Archive Creation

| Method | Endpoint                    | Description          |
| ------ | --------------------------- | -------------------- |
| POST   | `/api/v1/create-zip`        | Create ZIP archive   |
| GET    | `/api/v1/create-zip/status` | Check ZIP job status |

### PDF Splitting

| Method | Endpoint                   | Description               |
| ------ | -------------------------- | ------------------------- |
| POST   | `/api/v1/split-pdf`        | Split PDF by pages/labels |
| GET    | `/api/v1/split-pdf/status` | Check split job status    |

### Webhook Management

| Method | Endpoint                            | Description                 |
| ------ | ----------------------------------- | --------------------------- |
| POST   | `/api/v1/webhook/regenerate-secret` | Generate new webhook secret |
| GET    | `/api/v1/webhook/secret-info`       | Get masked secret info      |
| POST   | `/api/v1/webhook/test`              | Test webhook endpoint       |

### Logs & Monitoring

| Method | Endpoint       | Description                                    |
| ------ | -------------- | ---------------------------------------------- |
| GET    | `/api/v1/logs` | Get job logs with filtering (master user only) |

**Full API documentation**: [docs/API.md](docs/API.md)

---

## ⚙️ Environment Setup

Create a `.env` file in the project root:

```bash
# Celery Configuration
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
CELERY_WORKER_CONCURRENCY=2  # Number of concurrent worker processes

# AWS S3 Configuration
AWS_S3_BUCKET_NAME=your-pdf-bucket
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_PRESIGNED_URL_EXPIRY=3600  # Presigned URL expiry in seconds (default: 3600 = 1 hour, max: 604800 = 7 days)

# Environment
ENV=production  # or 'local'

# JWT Configuration
JWT_SECRET_KEY=your_super_secret_jwt_key_min_32_chars
JWT_ACCESS_TOKEN_EXPIRES=86400  # JWT token expiry in seconds (default: 86400 = 24 hours)

# Master User Credentials (auto-created on first run)
# Only the master user can register new users and access logs
MASTER_USERNAME=admin
MASTER_PASSWORD=change_this_in_production

# Database Configuration
POSTGRES_USER=your_postgres_user
POSTGRES_PASSWORD=your_postgres_password
POSTGRES_DB=pdf_toolkit
POSTGRES_HOST=postgres  # Database host (default: postgres for Docker)
# DATABASE_URL=postgresql://user:pass@host:5432/db  # Optional: overrides individual postgres vars
SQLALCHEMY_ECHO=False  # Enable SQL query logging for debugging (default: False)

# ClickHouse Configuration (for Vector logging service)
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=your_clickhouse_password
CLICKHOUSE_DATABASE=default
CLICKHOUSE_ENDPOINT=https://your-clickhouse-instance.com

# Limits Configuration
MAX_DOWNLOADS_PER_JOB=1000  # Maximum number of documents that can be downloaded per job
MAX_DOWNLOAD_SIZE_MB=1024  # Maximum download size per document in MB
MAX_QUEUED_REQUESTS=1000  # Maximum number of requests that can be queued

# Logging Configuration
LOG_LEVEL=INFO  # Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL (default: INFO)
```

### Environment Variable Reference

| Variable                    | Required | Default    | Description                                       |
| --------------------------- | -------- | ---------- | ------------------------------------------------- |
| **Celery**                  |          |            |                                                   |
| `CELERY_BROKER_URL`         | Yes      | -          | Redis URL for Celery broker                       |
| `CELERY_RESULT_BACKEND`     | Yes      | -          | Redis URL for Celery results                      |
| `CELERY_WORKER_CONCURRENCY` | No       | 2          | Number of concurrent worker processes             |
| **AWS S3**                  |          |            |                                                   |
| `AWS_S3_BUCKET_NAME`        | Yes      | -          | S3 bucket name for file storage                   |
| `AWS_REGION`                | Yes      | -          | AWS region (e.g., us-east-1)                      |
| `AWS_ACCESS_KEY_ID`         | Yes      | -          | AWS access key ID                                 |
| `AWS_SECRET_ACCESS_KEY`     | Yes      | -          | AWS secret access key                             |
| `AWS_PRESIGNED_URL_EXPIRY`  | No       | 3600       | Presigned URL expiry in seconds (max: 604800)     |
| **JWT**                     |          |            |                                                   |
| `JWT_SECRET_KEY`            | Yes      | -          | Secret key for JWT token signing (min 32 chars)   |
| `JWT_ACCESS_TOKEN_EXPIRES`  | No       | 86400      | JWT token expiry in seconds (24 hours)            |
| **Authentication**          |          |            |                                                   |
| `MASTER_USERNAME`           | Yes      | -          | Master user username (can register new users)     |
| `MASTER_PASSWORD`           | Yes      | -          | Master user password                              |
| **Database**                |          |            |                                                   |
| `POSTGRES_USER`             | Yes      | -          | PostgreSQL username                               |
| `POSTGRES_PASSWORD`         | Yes      | -          | PostgreSQL password                               |
| `POSTGRES_DB`               | Yes      | -          | PostgreSQL database name                          |
| `POSTGRES_HOST`             | No       | postgres   | PostgreSQL host                                   |
| `DATABASE_URL`              | No       | -          | Full database URL (overrides individual vars)     |
| `SQLALCHEMY_ECHO`           | No       | False      | Enable SQL query logging                          |
| **ClickHouse (Vector)**     |          |            |                                                   |
| `CLICKHOUSE_USER`           | No       | -          | ClickHouse username for Vector logging            |
| `CLICKHOUSE_PASSWORD`       | No       | -          | ClickHouse password                               |
| `CLICKHOUSE_DATABASE`       | No       | -          | ClickHouse database name                          |
| `CLICKHOUSE_ENDPOINT`       | No       | -          | ClickHouse endpoint URL                           |
| **Limits**                  |          |            |                                                   |
| `MAX_DOWNLOADS_PER_JOB`     | No       | 1000       | Max documents per job                             |
| `MAX_DOWNLOAD_SIZE_MB`      | No       | 1024       | Max download size per document (MB)               |
| `MAX_QUEUED_REQUESTS`       | No       | 1000       | Max requests that can be queued                   |
| **Application**             |          |            |                                                   |
| `ENV`                       | No       | production | Environment (production/local)                    |
| `LOG_LEVEL`                 | No       | INFO       | Logging level (DEBUG/INFO/WARNING/ERROR/CRITICAL) |

**Security Notes**:

- Never commit `.env` to version control
- Use environment-specific files (`.env.production`, `.env.staging`)
- Inject secrets via CI/CD or secret management systems
- Rotate credentials regularly
- Use strong passwords (16+ characters)

---

## 🐳 Deployment

### Docker Compose (Recommended)

```bash
# Production deployment
docker-compose -f docker-compose.yml up -d

# Scale workers
docker-compose up -d --scale worker=3

# View logs
docker-compose logs -f worker

# Stop services
docker-compose down
```

## 🧪 Testing

```bash
# Run all tests
python run_tests.py

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest app/tests/test_split_pdf_api.py -v

# Run specific test
pytest app/tests/test_api.py::test_generate_pdf -v
```

**Test Coverage:**

- ✅ API endpoints (auth, generation, merging, zipping, splitting)
- ✅ Database operations
- ✅ Webhook authentication
- ✅ PDF generation, merging, and splitting logic
- ✅ ZIP archive creation logic
- ✅ Error handling

See [docs/TESTING.md](docs/TESTING.md) for detailed testing guide.

---

## 📁 Project Structure

```
pdf-toolkit/
├── app/
│   ├── __init__.py              # Flask app initialization
│   ├── main.py                  # Application entry point
│   ├── database.py              # Database utilities
│   ├── api/                     # API blueprints
│   │   ├── auth.py              # Authentication endpoints
│   │   ├── pdf_generation.py   # PDF generation endpoints
│   │   ├── merge_pdf.py         # PDF merging endpoints
│   │   ├── zip_files.py         # ZIP creation endpoints
│   │   ├── split_pdf.py         # PDF splitting endpoints
│   │   ├── webhook.py           # Webhook management
│   │   └── logs.py              # Logging endpoints
│   ├── models/                  # Database models
│   │   ├── user.py              # User model
│   │   └── pdf_job.py           # Job & split models
│   ├── services/                # Business logic
│   │   ├── pdf_generator.py    # PDF generation service
│   │   ├── pdf_merger.py        # PDF merging service
│   │   ├── zip_creator.py       # ZIP creation service
│   │   ├── pdf_splitter.py      # PDF splitting service
│   │   ├── upload_handler.py    # S3/upload service
│   │   └── webhook_notifier.py  # Webhook service
│   ├── workers/                 # Celery tasks
│   │   └── celery_worker.py    # Async task definitions
│   ├── middleware/              # Middleware
│   │   └── auth.py              # JWT authentication
│   └── tests/                   # Test suite
│       ├── conftest.py          # Test fixtures
│       ├── test_api.py          # API tests
│       ├── test_merge_pdf_api.py
│       ├── test_zip_files_api.py
│       ├── test_split_pdf_api.py
│       ├── test_webhook.py
│       └── ...
├── docs/                        # Documentation
│   ├── API.md                   # API reference
│   ├── WEBHOOKS.md              # Webhook guide
│   ├── ARCHITECTURE.md          # System architecture
│   ├── DEPLOYMENT.md            # Deployment guide
│   ├── DEVELOPMENT.md           # Development guide
│   └── TESTING.md               # Testing guide
├── docker-compose.yml           # Docker orchestration
├── Dockerfile                   # Container definition
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment template
└── README.md                    # This file
```

---

## 🔒 Security

### Best Practices Implemented

✅ **JWT Authentication**: Secure token-based auth
✅ **Password Hashing**: bcrypt with salt
✅ **Webhook Signing**: HMAC-SHA256 signatures
✅ **Input Validation**: Request schema validation
✅ **SQL Injection Prevention**: ORM with parameterized queries
✅ **CORS Headers**: Configurable CORS policy
✅ **Rate Limiting**: (Recommended: Add nginx rate limiting)
✅ **Secrets Management**: Environment-based configuration

### Security Checklist

- [ ] Change default admin password
- [ ] Use strong JWT secret (32+ chars)
- [ ] Enable HTTPS in production
- [ ] Configure firewall rules
- [ ] Set up rate limiting
- [ ] Enable audit logging
- [ ] Rotate webhook secrets regularly
- [ ] Use AWS IAM roles (not access keys)
- [ ] Keep dependencies updated

---

## 🛠️ Technologies

| Category           | Technology                       |
| ------------------ | -------------------------------- |
| **Backend**        | Python 3.10, Flask 2.x           |
| **Task Queue**     | Celery 5.x, Redis                |
| **Database**       | SQLAlchemy, PostgreSQL           |
| **PDF Processing** | PyMuPDF (fitz), UnoServer 3.3.2  |
| **Cloud Storage**  | AWS S3, boto3                    |
| **Authentication** | PyJWT, bcrypt                    |
| **Testing**        | pytest, pytest-flask             |
| **Deployment**     | Docker, Docker Compose           |

---

## 📊 Performance

### Benchmarks (This is just template. Will be updated with latest data after putting in production)

| Operation              | Time | Throughput       |
| ---------------------- | ---- | ---------------- |
| Simple PDF generation  | 1.2s | ~50 docs/min     |
| Dynamic PDF (10 pages) | 2.5s | ~24 docs/min     |
| PDF split (100 pages)  | 0.8s | ~75 splits/min   |
| S3 upload (5MB)        | 0.4s | ~150 uploads/min |

### Scaling

- **Horizontal**: Scale Celery workers via `docker-compose up --scale worker=N`
- **Vertical**: Increase worker memory for large PDFs
- **Queue**: Redis can handle 100K+ jobs/sec
- **Storage**: S3 provides unlimited storage

---

## 🤝 Contributing

We welcome contributions! Please follow these guidelines:

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/amazing-feature`
3. **Write tests** for new functionality
4. **Ensure tests pass**: `pytest`
5. **Commit changes**: `git commit -m 'Add amazing feature'`
6. **Push to branch**: `git push origin feature/amazing-feature`
7. **Open a Pull Request**

### Code Style

- Follow PEP 8 guidelines
- Use type hints where possible
- Write docstrings for public functions
- Keep functions under 50 lines
- Test coverage > 80%

---

## 📝 License

This project is licensed under the MIT License

---

## 🆘 Support

- **Documentation**: [docs/](docs/)
- **Issues**: [GitHub Issues](`<repository-url>`/issues)
- **Email**: anandvikar@houseworksinc.co

---

## 📜 Changelog

### v3.0.0 (2025-10-07)

- ✨ Added PDF merging from multiple PDFs and images
- ✨ Added ZIP archive creation from any file types
- 🔧 Integrated PyMuPDF for native PDF merging
- 🔧 Consistent API parameter naming (document_urls)
- 📚 Updated documentation for new features
- ✅ Added comprehensive tests for merge and ZIP operations

### v2.0.0 (2025-10-03)

- ✨ Added PDF splitting by pages and labels
- ✨ Implemented webhook system with HMAC authentication
- ✨ Added user management with JWT auth
- 🔧 Migrated to modular blueprint architecture
- 📚 Complete documentation overhaul
- 🐛 Fixed Celery worker module path

### v1.0.0 (2025-09-01)

- 🎉 Initial release
- ✨ PDF generation from DOCX templates
- ✨ Dynamic content support
- ✨ S3 storage integration
- ✨ Celery async processing

---

<div align="center">

**Built with ❤️ by the HouseWorks Team**

[Documentation](docs/) • [API Reference](docs/API.md) • [Report Bug](`<repository-url>`/issues)

</div>
