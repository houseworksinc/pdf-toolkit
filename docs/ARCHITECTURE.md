# System Architecture

Detailed architecture documentation for HouseWorks PDF Toolkit.

---

## System Overview

```
┌──────────────────────────────────────────────────────────────┐
│                      CLIENT APPLICATIONS                      │
│  (Web Apps, Mobile Apps, Backend Services, Scripts)          │
└────────────────┬─────────────────────────────────────────────┘
                 │ HTTPS + JWT Token
                 ▼
┌──────────────────────────────────────────────────────────────┐
│                    FLASK API GATEWAY                          │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Blueprint Routers:                                    │  │
│  │  • /api/v1/auth                  - Authentication & User Mgmt │  │
│  │  • /api/v1/generate-pdf          - PDF Generation             │  │
│  │  • /api/v1/merge-pdfs            - PDF Merging                │  │
│  │  • /api/v1/create-zip            - ZIP Archive Creation       │  │
│  │  • /api/v1/split-pdf             - PDF Splitting              │  │
│  │  • /api/v1/process-and-merge-pdfs - Process & Merge PDFs     │  │
│  │  • /api/v1/webhook               - Webhook Management         │  │
│  │  • /api/v1/logs                  - Job Logs & Monitoring      │  │
│  └────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Middleware Layer:                                     │  │
│  │  • JWT Auth (require_jwt_token)                       │  │
│  │  • Request Validation                                  │  │
│  │  • Error Handling                                      │  │
│  │  • Logging                                             │  │
│  └────────────────────────────────────────────────────────┘  │
└────────────────┬─────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────┐
│                      CELERY WORKERS                           │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Async Tasks:                                          │  │
│  │  • generate_pdf_task         - Static template fill   │  │
│  │  • generate_pdf_dynamic_task - Dynamic content        │  │
│  │  • merge_pdfs_task           - PDF merging            │  │
│  │  • create_zip_task           - ZIP archive creation   │  │
│  │  • split_pdf_task            - PDF splitting          │  │
│  │  • process_and_merge_task    - Generate + Merge PDFs  │  │
│  └────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Services:                                             │  │
│  │  • pdf_generator.py   - DOCX → PDF conversion         │  │
│  │  • pdf_merger.py      - Multi-doc merging (PyMuPDF)   │  │
│  │  • zip_creator.py     - ZIP archive creation          │  │
│  │  • pdf_splitter.py    - PyMuPDF splitting logic       │  │
│  │  • upload_handler.py  - S3 & presigned URL uploads    │  │
│  │  • webhook_notifier.py - HMAC-signed notifications    │  │
│  └────────────────────────────────────────────────────────┘  │
└─────┬──────────────┬──────────────┬──────────────┬───────────┘
      │              │              │              │
      ▼              ▼              ▼              ▼
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐
│  REDIS   │  │   S3     │  │ SQLite   │  │   Webhooks   │
│  Queue   │  │  Store   │  │    DB    │  │   (Client)   │
│          │  │          │  │          │  │              │
│ •Tasks   │  │ •PDFs    │  │ •Jobs    │  │ •Callbacks   │
│ •Results │  │ •Merged  │  │ •Users   │  │ •HMAC-256    │
│          │  │ •ZIPs    │  │ •Splits  │  │              │
│          │  │ •Splits  │  │          │  │              │
└──────────┘  └──────────┘  └──────────┘  └──────────────┘
```

## Component Details

### 1. Flask API (Port 5001)

- **Role**: HTTP API gateway
- **Technology**: Flask 2.x
- **Responsibilities**:
  - Request routing & validation
  - JWT authentication
  - Job creation & queuing
  - Status queries

### 2. Celery Workers

- **Role**: Async task execution
- **Technology**: Celery 5.x
- **Broker**: Redis
- **Concurrency**: Configurable (default: 4 per worker)

**Priority Queue System:**
- **3 Priority Levels**: High (0), Medium (1), Low (2)
- **Queue Order**: `high_priority` → `medium_priority` → `low_priority`
- **Worker Behavior**: Always checks high priority queue first, then medium, then low
- **Configuration**: `docker-compose.yml` line 71: `--queues=high_priority,medium_priority,low_priority`
- **Override**: API requests can specify `priority` to route tasks to specific queues

### 3. Redis (Port 6379)

- **Role**: Message broker + result backend
- **Technology**: Redis 7.x Alpine
- **Persistence**: AOF + RDB snapshots

### 4. SQLite Database

- **Role**: Job logging & user management
- **File**: `pdf-toolkit.db`
- **Models**:
  - `User`: Authentication & webhook secrets
  - `PdfJob`: Job metadata & status
  - `PdfSplitOutput`: Individual split results

### 5. AWS S3

- **Role**: PDF, merged PDF, ZIP, and split PDF storage
- **Access**: IAM credentials or IAM roles
- **Features**: Presigned URLs (1-hour expiry)
- **Storage Paths**:
  - Generated PDFs: `pdfs/{client_job_id}.pdf`
  - Merged PDFs: `pdfs/merged/{client_job_id}.pdf`
  - ZIP Archives: `zips/{client_job_id}.zip`
  - Split PDFs: `pdfs/splits/{client_job_id}/{filename}.pdf`

### 6. Template Cache

- **Role**: Cache frequently used DOCX templates to reduce download latency
- **Technology**: Redis (metadata) + Filesystem (files)
- **Storage**: Shared Docker volume (`template_cache`)
- **Features**:
  - Hash-based template identification
  - TTL-based expiration (default: 7 days, refreshed on access)
  - Size-based LRU eviction (default: 500 MB max)
  - Automatic cleanup via Celery Beat

**How It Works:**
1. Client includes optional `template_hash` in PDF generation request
2. If hash provided → check cache (Redis metadata + file existence)
3. Cache HIT → copy cached template to working directory
4. Cache MISS → download template, store in cache for future use
5. No hash provided → direct download (no caching)

**Configuration:**
- `TEMPLATE_CACHE_ENABLED`: Enable/disable caching (default: `true`)
- `TEMPLATE_CACHE_DIR`: Cache directory (default: `/app/template_cache`)
- `TEMPLATE_CACHE_MAX_SIZE_MB`: Max cache size (default: `500`)
- `TEMPLATE_CACHE_TTL_DAYS`: TTL in days (default: `7`)

### 7. UnoServer

- **Role**: Document conversion (DOCX, XLSX, PPTX, ODT, etc.) → PDF
- **Technology**: LibreOffice via UNO API (XML-RPC)
- **Container**: Dedicated `ghcr.io/unoconv/unoserver-docker:latest`
- **Port**: 2003 (internal network only)
- **Performance**: ~0.5-1.5s per conversion (30-50% faster than CLI)
- **Benefits**:
  - Persistent process (no startup overhead)
  - Lower CPU usage (no process spawning)
  - Better resource management
  - Automatic health checks

#### UnoServer Architecture

```
┌─────────────────────────────────────────┐
│  Application Containers                 │
│  ┌────────────────────────────────────┐ │
│  │  Flask API / Celery Workers        │ │
│  │                                    │ │
│  │  • pdf_generator.py                │ │
│  │  • pdf_orchestrator.py             │ │
│  │  • pdf_merger.py                   │ │
│  │                                    │ │
│  │  UnoServerConverter                │ │
│  │    ↓                               │ │
│  │  [TCP:2003] UNO API Call           │ │
│  └────────────────┬───────────────────┘ │
└───────────────────┼─────────────────────┘
                    │ Internal Network
                    ▼
┌─────────────────────────────────────────┐
│  UnoServer Container                    │
│  ┌────────────────────────────────────┐ │
│  │  unoserver daemon                  │ │
│  │    ↓                               │ │
│  │  LibreOffice (headless)            │ │
│  │    • Writer  (DOCX, ODT, RTF)      │ │
│  │    • Calc    (XLSX, ODS, CSV)      │ │
│  │    • Impress (PPTX, ODP)           │ │
│  │    • Draw    (ODG, VSD, VSDX)      │ │
│  │                                    │ │
│  │  ↓ Output                          │ │
│  │  PDF Files                         │ │
│  └────────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

**Conversion Flow:**
1. Application calls `UnoServerConverter.convert_to_pdf()`
2. Converter checks UnoServer availability via socket
3. Reads input file as binary data
4. Sends XML-RPC request to UnoServer (port 2003)
5. UnoServer invokes LibreOffice for conversion
6. Returns PDF as binary data
7. Converter writes PDF to output directory

**Supported Formats:**
- **Documents**: DOC, DOCX, ODT, RTF, TXT, EPUB, FB2, HTML, HTM, WPD
- **Spreadsheets**: XLS, XLSX, XLSM, ODS, CSV, TSV
- **Presentations**: PPT, PPTX, ODP
- **Drawings**: ODG, VSD, VSDX

**Configuration (docker-compose.yml):**
```yaml
unoserver:
  image: ghcr.io/unoconv/unoserver-docker:latest
  expose:
    - "2003"  # Internal only - no external exposure
  networks:
    - app-network
  healthcheck:
    test: ["CMD", "python", "-c", "import socket; s=socket.socket(); s.connect(('127.0.0.1', 2003)); s.close()"]
    interval: 10s
    timeout: 5s
    retries: 5
    start_period: 30s  # LibreOffice initialization time
```

**Environment Variables:**
- `UNOSERVER_HOST`: Hostname (default: `unoserver`)
- `UNOSERVER_PORT`: Port (default: `2003`)
- `UNO_SERVER_TIMEOUT`: Conversion timeout in seconds (default: `60`)

## Data Flow Diagrams

### PDF Generation Flow

```
User Request
    │
    ▼
[API: Validate Request]
    │
    ▼
[DB: Log Job → PENDING]
    │
    ▼
[Celery: Queue Task]
    │
    ├─────────────────────────┐
    │                         ▼
[API: Return task_id]   [Worker: Start Processing]
                             │
                             ▼
                        [DB: Update → PROCESSING]
                             │
                             ▼
                        [Check Template Cache]
                             │
                        ┌────┴────┐
                        │ HIT?    │
                        └────┬────┘
                    YES │         │ NO
                        ▼         ▼
                  [Use Cached] [Download & Cache]
                        │         │
                        └────┬────┘
                             ▼
                        [Fill Template with Data]
                             │
                             ▼
                        [UnoServer: DOCX → PDF]
                             │
                             ▼
                        [Upload to S3]
                             │
                             ▼
                        [DB: Update → SUCCESS]
                             │
                             ▼
                        [Send Webhook (if configured)]
```

### PDF Splitting Flow

```
User Request + Webhook URL
    │
    ▼
[API: Validate splits config]
    │
    ▼
[DB: Log Job + Splits → PENDING]
    │
    ▼
[Celery: Queue split_pdf_task]
    │
    ├─────────────────────────┐
    │                         ▼
[API: Return task_id]   [Worker: Start Processing]
                             │
                             ▼
                        [DB: Update → PROCESSING]
                             │
                             ▼
                        [Download Source PDF]
                             │
                             ▼
                        [PyMuPDF: Open Document]
                             │
                             ▼
                    ┌───────┴────────┐
                    │  For Each Split │
                    └───────┬────────┘
                            │
                    ┌───────▼────────┐
                    │ Split PDF      │
                    │ Upload to S3   │
                    │ Update DB      │
                    │ Send Webhook   │
                    └───────┬────────┘
                            │
                            ▼
                    [All Splits Done?]
                            │
                            ▼
                    [DB: Update → SUCCESS/PARTIAL/FAILURE]
                            │
                            ▼
                    [Send Final Webhook]
```

### PDF Merging Flow

```
User Request + Documents
    │
    ▼
[API: Validate document_urls]
    │
    ▼
[DB: Log Job → PENDING]
    │
    ▼
[Celery: Queue merge_pdfs_task]
    │
    ├─────────────────────────┐
    │                         ▼
[API: Return task_id]   [Worker: Start Processing]
                             │
                             ▼
                        [DB: Update → PROCESSING]
                             │
                             ▼
                        [Download All Documents]
                             │
                             ▼
                        [PyMuPDF: Merge PDFs/Images]
                             │
                             ▼
                        [Upload to S3 (pdfs/merged/)]
                             │
                             ▼
                        [DB: Update → SUCCESS]
                             │
                             ▼
                        [Send Webhook (if configured)]
```

### ZIP Archive Creation Flow

```
User Request + Files
    │
    ▼
[API: Validate document_urls]
    │
    ▼
[DB: Log Job → PENDING]
    │
    ▼
[Celery: Queue create_zip_task]
    │
    ├─────────────────────────┐
    │                         ▼
[API: Return task_id]   [Worker: Start Processing]
                             │
                             ▼
                        [DB: Update → PROCESSING]
                             │
                             ▼
                        [Download All Files]
                             │
                             ▼
                        [Create ZIP Archive]
                             │
                             ▼
                        [Upload to S3 (zips/)]
                             │
                             ▼
                        [DB: Update → SUCCESS]
                             │
                             ▼
                        [Send Webhook (if configured)]
```

## Database Schema

### User Table

```sql
CREATE TABLE users (
    id VARCHAR(36) PRIMARY KEY,  -- UUID
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    meta_data TEXT,
    webhook_secret VARCHAR(64),
    webhook_secret_created_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT 1
);
```

### PdfJob Table

```sql
CREATE TABLE pdf_jobs (
    id VARCHAR(36) PRIMARY KEY,  -- UUID
    client_job_id VARCHAR(255) UNIQUE NOT NULL,
    task_id VARCHAR(255),
    job_type VARCHAR(50) NOT NULL,  -- 'generate', 'merge', 'zip', 'split', 'process_and_merge'
    documents TEXT,  -- JSON array (unified schema for all document types)
    output_filename VARCHAR(255),
    webhook_url TEXT,
    meta_data TEXT,  -- JSON
    request_data TEXT,  -- JSON
    status VARCHAR(50) DEFAULT 'PENDING',
    s3_key TEXT,
    download_url TEXT,
    error TEXT,
    exception_type VARCHAR(255),
    processing_time FLOAT,
    started_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    ended_at DATETIME
);
```

### PdfSplitOutput Table

```sql
CREATE TABLE pdf_split_outputs (
    id VARCHAR(36) PRIMARY KEY,  -- UUID
    pdf_job_id VARCHAR(36) NOT NULL,  -- Foreign key to pdf_jobs.id
    file_name VARCHAR(255) NOT NULL,
    pages TEXT,  -- JSON array
    labels TEXT,  -- JSON array
    meta_data TEXT,  -- JSON
    file_upload_url TEXT,
    s3_key TEXT,
    download_url TEXT,
    status VARCHAR(50) DEFAULT 'PENDING',
    error TEXT,
    processing_time FLOAT,
    file_size INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    ended_at DATETIME,
    FOREIGN KEY (pdf_job_id) REFERENCES pdf_jobs(id) ON DELETE CASCADE
);
```

## Security Architecture

### Authentication Flow

```
1. User Registration
   └─> Bcrypt hash password (cost: 12)
   └─> Generate webhook secret (32 bytes, URL-safe)
   └─> Store in DB

2. User Login
   └─> Verify password with bcrypt
   └─> Generate JWT token (HS256)
   └─> Return token to client

3. API Request
   └─> Extract Bearer token
   └─> Verify JWT signature & expiry
   └─> Load user from DB
   └─> Proceed to endpoint
```

### Webhook Security

```
1. Generate Webhook Secret (on user creation)
   └─> token_urlsafe(32) → 43-char string

2. Send Webhook
   └─> Sort payload keys
   └─> JSON stringify (no spaces)
   └─> HMAC-SHA256(payload, secret)
   └─> Add X-Webhook-Signature header

3. Client Verification
   └─> Receive webhook
   └─> Recompute HMAC-SHA256
   └─> Compare with header (timing-safe)
   └─> Process only if match
```

## Scaling Strategies

### Horizontal Scaling

**Celery Workers:**

```bash
docker-compose up -d --scale worker=5
```

**Flask API (via Kubernetes):**

```yaml
replicas: 3
resources:
  requests:
    cpu: 500m
    memory: 512Mi
  limits:
    cpu: 1000m
    memory: 1Gi
```

### Vertical Scaling

| Component      | CPU     | Memory | Storage |
| -------------- | ------- | ------ | ------- |
| API (small)    | 1 core  | 512MB  | -       |
| API (medium)   | 2 cores | 1GB    | -       |
| Worker (small) | 1 core  | 1GB    | -       |
| Worker (large) | 4 cores | 4GB    | -       |
| Redis          | 1 core  | 256MB  | 1GB     |

### Performance Optimization

1. **Connection Pooling**: SQLAlchemy pool (size: 10)
2. **Redis Pipelining**: Batch queue operations
3. **S3 Multipart Upload**: For files > 5MB
4. **UnoServer Persistence**: Dedicated container eliminates process startup overhead
5. **Template Caching**: Cache frequently used templates

## Monitoring & Observability

### Key Metrics

- **API**: Request rate, latency (p50, p95, p99), error rate
- **Celery**: Queue depth, task duration, success/failure rate
- **Redis**: Memory usage, hit rate, connection count
- **S3**: Upload success rate, bandwidth

### Logging

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)
logger.info(f"Processing job {client_job_id}")
```

### Health Checks

```python
@app.route("/health")
def health():
    return {
        "status": "healthy",
        "redis": check_redis(),
        "s3": check_s3(),
        "database": check_database()
    }
```

## Disaster Recovery

### Backup Strategy

1. **Database**: Daily SQLite backup to S3
2. **Redis**: AOF + RDB snapshots
3. **S3**: Versioning enabled + lifecycle policy

### Recovery Procedures

1. **API Failure**: Load balancer auto-routes to healthy instances
2. **Worker Failure**: Celery auto-retries tasks (max: 3 attempts)
3. **Redis Failure**: Restart from RDB snapshot (< 5 min data loss)
4. **S3 Outage**: Retry uploads with exponential backoff

---

## Technology Decisions

### Why Flask?

- Lightweight & fast
- Excellent ecosystem
- Easy to test & deploy
- Blueprint architecture (modularity)

### Why Celery?

- Battle-tested at scale
- Rich ecosystem
- Flexible routing
- Monitoring tools (Flower)

### Why Redis?

- In-memory speed
- Pub/sub capabilities
- Persistence options
- Simple operations

### Why SQLite?

- Zero configuration
- File-based (easy backups)
- Fast for reads
- Sufficient for < 1M jobs

### Why PyMuPDF (fitz)?

- 10x faster than PyPDF2
- Native PDF merging and splitting
- Preserves page labels
- Image-to-PDF conversion
- Low memory footprint
- Active development

---

For deployment details, see [DEPLOYMENT.md](DEPLOYMENT.md)
