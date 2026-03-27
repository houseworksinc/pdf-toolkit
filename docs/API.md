# API Reference

Complete API documentation for HouseWorks PDF Toolkit v2.0

---

## Table of Contents

- [Authentication](#authentication)
- [PDF Generation](#pdf-generation)
- [PDF Merging](#pdf-merging)
- [Process and Merge PDFs](#process-and-merge-pdfs)
- [Process and ZIP](#process-and-zip)
- [ZIP Archive Creation](#zip-archive-creation)
- [PDF Splitting](#pdf-splitting)
- [Webhook Management](#webhook-management)
- [Logs &amp; Monitoring](#logs--monitoring)
- [Error Handling](#error-handling)
- [Rate Limits](#rate-limits)

---

## Base URL

```
Production: https://api.houseworks.com
Development: http://localhost:5001
```

## Authentication

All endpoints (except `/api/v1/auth/register` and `/api/v1/auth/login`) require JWT authentication.

**Header Format:**

```
Authorization: Bearer <jwt_token>
```

### Register User

```http
POST /api/v1/auth/register
```

**Request Body:**

```json
{
  "username": "johndoe",
  "password": "SecureP@ss123",
  "meta_data": {
    // Optional
    "company": "Acme Corp",
    "role": "admin"
  }
}
```

**Response (201 Created):**

```json
{
  "message": "User registered successfully",
  "username": "johndoe",
  "user_id": 5,
  "webhook_secret": "a1b2c3d4e5f6g7h8...",
  "warning": "⚠️ Save the webhook_secret securely - it won't be shown again!"
}
```

### Login

```http
POST /api/v1/auth/login
```

**Request Body:**

```json
{
  "username": "johndoe",
  "password": "SecureP@ss123"
}
```

**Response (200 OK):**

```json
{
  "message": "Login successful",
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "id": 5,
    "username": "johndoe"
  }
}
```

**Token Expiry:** Default 24 hours (configurable via `JWT_ACCESS_TOKEN_EXPIRES`)

### Verify Token

```http
GET /api/v1/auth/authenticate
Authorization: Bearer <token>
```

**Response (200 OK):**

```json
{
  "message": "Token is valid",
  "user": {
    "id": 5,
    "username": "johndoe"
  }
}
```

---

## PDF Generation

**Important**: All job creation endpoints return a `job_id` (UUID) in the response. Save this `job_id` to check job status later using the status endpoints.

### Task Priority (Optional)

All endpoints support an optional `priority` parameter to control task processing order:

```json
{
  "priority": 0  // 0=High, 1=Medium (default), 2=Low
}
```

**Priority Levels:**
- `0` (High): Processed first - for time-sensitive operations
- `1` (Medium): Default priority - for normal operations
- `2` (Low): Processed last - for background/bulk operations

**Default Priorities:**
- Generate PDF tasks: High (0)
- Split/Merge/ZIP tasks: Medium (1)
- Process-and-Merge/ZIP tasks: Low (2)

Omit `priority` to use the default for each task type.

### Generate PDF (Static)

Simple template placeholder replacement.

```http
POST /api/v1/generate-pdf
Authorization: Bearer <token>
Content-Type: application/json
```

**Request Body:**

```json
{
  "client_job_id": "INV-2025-001",
  "template_url": "https://storage.example.com/invoice-template.docx",
  "template_hash": "abc123def456",
  "data": {
    "company_name": "Acme Corporation",
    "invoice_number": "INV-2025-001",
    "date": "2025-10-03",
    "customer_name": "John Doe",
    "items": [
      {
        "description": "Service A",
        "quantity": 2,
        "price": 100.0
      },
      {
        "description": "Service B",
        "quantity": 1,
        "price": 250.0
      }
    ],
    "total": 450.0,
    "logo_image_url": "https://example.com/logo.png"
  }
}
```

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `client_job_id` | string | Yes | Unique identifier for the job |
| `template_url` | string | Yes | URL to the DOCX template |
| `template_hash` | string | No | Hash for template caching (see below) |
| `data` | object | Yes | JSON data to fill into template |
| `webhook` | string | No | URL for completion webhook |
| `meta_data` | object | No | Custom metadata |

**Template Caching (`template_hash`):**

When provided, the system caches the template file for faster subsequent requests:
- First request with hash: downloads and caches the template
- Subsequent requests with same hash: uses cached version (faster)
- Cache TTL refreshes on each access (default: 7 days)
- Generate the hash client-side (e.g., SHA-256 of template URL or content)

**Response (202 Accepted):**

```json
{
  "status": "queued",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "client_job_id": "INV-2025-001",
  "task_id": "e3f2a1b5-4c3d-2e1f-0a9b-8c7d6e5f4a3b"
}
```

### Generate PDF (Dynamic)

Advanced content generation with rich formatting.

```http
POST /api/v1/generate-pdf/dynamic
Authorization: Bearer <token>
Content-Type: application/json
```

**Request Body:**

```json
{
  "client_job_id": "REPORT-2025-Q3",
  "template_url": "https://storage.example.com/report-template.docx",
  "template_hash": "xyz789ghi012",
  "output_filename": "quarterly_report_q3_2025",
  "data": {
    "report_title": "Q3 2025 Financial Report",
    "company": "Acme Corp",
    "report_body": {
      "data-type": "pre-formatted",
      "content": [
        {
          "type": "heading",
          "style": "Heading 1",
          "data": { "text": "Executive Summary" }
        },
        {
          "type": "paragraph",
          "data": {
            "runs": [
              { "text": "Revenue increased by ", "bold": false },
              { "text": "23%", "bold": true, "color": "00AA00" },
              { "text": " compared to Q2 2025.", "bold": false }
            ]
          }
        },
        {
          "type": "list",
          "data": {
            "list_type": "bulleted",
            "items": [
              { "runs": [{ "text": "Total revenue: $1.2M", "bold": true }] },
              { "runs": [{ "text": "Net profit: $450K" }] },
              { "runs": [{ "text": "Customer growth: 15%" }] }
            ]
          }
        },
        {
          "type": "table",
          "style": "Light Grid Accent 1",
          "data": {
            "rows": [
              [
                { "runs": [{ "text": "Metric", "bold": true }] },
                { "runs": [{ "text": "Q2 2025", "bold": true }] },
                { "runs": [{ "text": "Q3 2025", "bold": true }] }
              ],
              [
                { "runs": [{ "text": "Revenue" }] },
                { "runs": [{ "text": "$975K" }] },
                { "runs": [{ "text": "$1.2M" }] }
              ]
            ]
          }
        }
      ]
    }
  }
}
```

**Response (202 Accepted):**

```json
{
  "status": "queued",
  "job_id": "550e8400-e29b-41d4-a716-446655440001",
  "client_job_id": "REPORT-2025-Q3",
  "task_id": "f4e3d2c1-5b4a-3c2d-1e0f-9a8b7c6d5e4f",
  "output_filename": "quarterly_report_q3_2025"
}
```

### Check PDF Status

Check the status of any PDF generation job (both static and dynamic).

```http
GET /api/v1/generate-pdf/status?job_id=INV-2025-001
Authorization: Bearer <token>
```

**Query Parameters:**

- `job_id` (required): The job UUID (primary key) to check status for. This UUID is returned in the `job_id` field when creating a job. Works for both static and dynamic PDF generation.

**Response (Processing):**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "client_job_id": "INV-2025-001",
  "task_id": "e3f2a1b5-4c3d-2e1f-0a9b-8c7d6e5f4a3b",
  "status": "PROCESSING",
  "documents": [
    {
      "type": "generate",
      "status": "queued",
      "meta_data": {}
    }
  ]
}
```

**Response (Success):**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "client_job_id": "INV-2025-001",
  "task_id": "e3f2a1b5-4c3d-2e1f-0a9b-8c7d6e5f4a3b",
  "status": "SUCCESS",
  "download_url": "https://s3.amazonaws.com/bucket/pdfs/INV-2025-001.pdf?...",
  "processing_time": 2.3,
  "documents": [
    {
      "type": "generate",
      "status": "completed",
      "started_at": "2025-10-03T10:00:00Z",
      "ended_at": "2025-10-03T10:00:02Z",
      "processing_time": 2.3,
      "meta_data": {}
    }
  ]
}
```

**Response (Failure):**

```json
{
  "client_job_id": "INV-2025-001",
  "task_id": "e3f2a1b5-4c3d-2e1f-0a9b-8c7d6e5f4a3b",
  "status": "FAILURE",
  "error": "Template file could not be downloaded",
  "documents": [
    {
      "type": "generate",
      "status": "failed",
      "error": "Template file could not be downloaded",
      "meta_data": {}
    }
  ]
}
```

**Error Responses:**

```json
{
  "error": "job_id query parameter is required"
}
```

```json
{
  "error": "Job not found"
}
```

---

## DOCX to PDF Conversion

### Convert DOCX to PDF (Synchronous)

**Synchronous endpoint** that converts a DOCX file to PDF and returns the result immediately. Unlike other endpoints, this blocks the HTTP request until conversion completes (typically 4-8 seconds).

```http
POST /api/v1/convert-docx-to-pdf
Authorization: Bearer <token>
Content-Type: application/json
```

**Request Body:**

```json
{
  "docx_url": "https://storage.example.com/document.docx",
  "client_job_id": "CONV-2025-001",
  "output_filename": "converted-document",
  "file_upload_url": "https://s3.amazonaws.com/presigned-upload-url"
}
```

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `docx_url` | string | Yes | HTTP/HTTPS URL to DOCX file (max 50MB) |
| `client_job_id` | string | No | Your tracking ID for this conversion |
| `output_filename` | string | No | Base name for output PDF (without .pdf extension) |
| `file_upload_url` | string | No | Optional presigned URL for uploading result. If not provided, uploads to S3. |

**Response (200 OK):**

```json
{
  "status": "completed",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "client_job_id": "CONV-2025-001",
  "download_url": "https://s3.amazonaws.com/bucket/pdfs/convert/550e8400-e29b-41d4-a716-446655440000.pdf?...",
  "s3_key": "pdfs/convert/550e8400-e29b-41d4-a716-446655440000.pdf",
  "file_size": 245678,
  "processing_time": 3.45,
  "output_filename": "converted-document.pdf"
}
```

**Error Responses:**

```json
{
  "error": "docx_url is required"
}
```

```json
{
  "error": "File must be a DOCX document"
}
```

```json
{
  "error": "PDF conversion service unavailable"
}
```

**Notes:**

- **Synchronous**: Request blocks until conversion completes (~4-8 seconds)
- **File Size Limit**: 50MB maximum
- **File Type**: Only `.docx` files are supported
- **No Status Endpoint**: Result is returned immediately (no polling needed)
- **No Webhooks**: Not supported for synchronous endpoint
- **No Priority**: Priority parameter not applicable

**Typical Use Case:**

Use this endpoint when you need immediate conversion results and can wait for the response. For high-volume or large files, consider using the async PDF generation endpoints instead.

---

## PDF Merging

### Merge PDFs

Merge multiple documents (PDFs and images) into a single PDF file.

```http
POST /api/v1/merge-pdfs
Authorization: Bearer <token>
Content-Type: application/json
```

**Request Body:**

```json
{
  "client_job_id": "MERGE-2025-001",
  "document_urls": [
    "https://storage.example.com/cover.pdf",
    "https://storage.example.com/logo.png",
    "https://storage.example.com/content.pdf",
    "https://storage.example.com/signature.jpg"
  ],
  "output_filename": "merged-document",
  "webhook": "https://yourapp.com/webhooks/pdf-merge",
  "file_upload_url": "https://s3.amazonaws.com/presigned-upload-url",
  "meta_data": {
    "project": "Q4-2025",
    "category": "reports"
  }
}
```

**Supported File Formats:**

- **PDFs**: `.pdf` (direct merge, fastest)
- **Images**: `.png`, `.jpg`, `.jpeg`, `.gif`, `.bmp`, `.tiff`, `.svg` (converted to PDF)

**Planned Support** (not yet implemented):

- **Documents**: `.docx`, `.doc`, `.odt`, `.rtf`, `.txt`, `.epub`, `.html`
- **Spreadsheets**: `.xlsx`, `.xls`, `.ods`, `.csv`, `.tsv`
- **Presentations**: `.pptx`, `.ppt`, `.odp`

**Response (200 OK):**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440002",
  "client_job_id": "MERGE-2025-001",
  "task_id": "m1n2o3p4-q5r6-s7t8-u9v0-w1x2y3z4a5b6",
  "status": "queued",
  "started_at": "2025-10-07T10:15:30Z",
  "meta_data": {
    "project": "Q4-2025",
    "category": "reports"
  }
}
```

### Check Merge Status

```http
GET /api/v1/merge-pdfs/status?job_id=MERGE-2025-001
Authorization: Bearer <token>
```

**Response (Queued):**

```json
{
  "client_job_id": "MERGE-2025-001",
  "task_id": "m1n2o3p4-q5r6-s7t8-u9v0-w1x2y3z4a5b6",
  "status": "queued",
  "started_at": "2025-10-07T10:15:30Z",
  "ended_at": null,
  "processing_time": null,
  "meta_data": {
    "project": "Q4-2025",
    "category": "reports"
  },
  "download_url": null,
  "documents": [
    {
      "type": "url",
      "document_url": "https://storage.example.com/cover.pdf",
      "status": "queued"
    },
    {
      "type": "url",
      "document_url": "https://storage.example.com/logo.png",
      "status": "queued"
    },
    {
      "type": "url",
      "document_url": "https://storage.example.com/content.pdf",
      "status": "queued"
    },
    {
      "type": "url",
      "document_url": "https://storage.example.com/signature.jpg",
      "status": "queued"
    }
  ]
}
```

**Response (Completed):**

```json
{
  "client_job_id": "MERGE-2025-001",
  "task_id": "m1n2o3p4-q5r6-s7t8-u9v0-w1x2y3z4a5b6",
  "status": "completed",
  "started_at": "2025-10-07T10:15:30Z",
  "ended_at": "2025-10-07T10:15:45Z",
  "processing_time": "15.2",
  "meta_data": {
    "project": "Q4-2025",
    "category": "reports"
  },
  "download_url": "https://s3.amazonaws.com/bucket/pdfs/merged/MERGE-2025-001.pdf?...",
  "documents": [
    {
      "type": "url",
      "document_url": "https://storage.example.com/cover.pdf",
      "status": "completed",
      "processing_time": 2.1
    },
    {
      "type": "url",
      "document_url": "https://storage.example.com/logo.png",
      "status": "completed",
      "processing_time": 1.8
    },
    {
      "type": "url",
      "document_url": "https://storage.example.com/content.pdf",
      "status": "completed",
      "processing_time": 3.2
    },
    {
      "type": "url",
      "document_url": "https://storage.example.com/signature.jpg",
      "status": "completed",
      "processing_time": 1.5
    }
  ]
}
```

**Response (Failed):**

```json
{
  "client_job_id": "MERGE-2025-001",
  "task_id": "m1n2o3p4-q5r6-s7t8-u9v0-w1x2y3z4a5b6",
  "status": "failed",
  "started_at": "2025-10-07T10:15:30Z",
  "ended_at": "2025-10-07T10:15:32Z",
  "processing_time": "2.1",
  "meta_data": {
    "project": "Q4-2025",
    "category": "reports"
  },
  "download_url": null,
  "error": "Failed to download file from https://storage.example.com/content.pdf: 404 Not Found",
  "documents": [
    {
      "type": "url",
      "document_url": "https://storage.example.com/cover.pdf",
      "status": "completed",
      "processing_time": 1.2
    },
    {
      "type": "url",
      "document_url": "https://storage.example.com/logo.png",
      "status": "completed",
      "processing_time": 0.8
    },
    {
      "type": "url",
      "document_url": "https://storage.example.com/content.pdf",
      "status": "failed",
      "error": "Failed to download file: 404 Not Found"
    },
    {
      "type": "url",
      "document_url": "https://storage.example.com/signature.jpg",
      "status": "queued"
    }
  ]
}
```

---

## Process and Merge PDFs

### Process and Merge PDFs

**Advanced Operation**: Generate PDFs from templates AND/OR download existing documents, then merge them all into a single PDF in one atomic operation.

This endpoint combines the power of PDF generation (both static and dynamic modes) with document downloading and merging. Perfect for creating comprehensive document packages that include both generated reports and existing files.

```http
POST /api/v1/process-and-merge-pdfs
Authorization: Bearer <token>
Content-Type: application/json
```

**Request Body:**

```json
{
  "client_job_id": "PROC-2025-001",
  "documents": [
    {
      "type": "url",
      "document_url": "https://storage.example.com/cover-page.pdf",
      "meta_data": {
        "label": "Cover Page",
        "section": "front-matter"
      }
    },
    {
      "type": "generate",
      "mode": "static",
      "template_url": "https://storage.example.com/invoice-template.docx",
      "template_hash": "abc123def456",
      "data": {
        "invoice_number": "INV-2025-001",
        "date": "2025-10-09",
        "customer_name": "Acme Corp",
        "total": 1250.0
      },
      "meta_data": {
        "label": "Invoice",
        "section": "billing"
      }
    },
    {
      "type": "generate",
      "mode": "dynamic",
      "template_url": "https://storage.example.com/report-template.docx",
      "template_hash": "xyz789ghi012",
      "output_filename": "quarterly_report",
      "data": {
        "report_title": "Q3 2025 Report",
        "report_body": {
          "data-type": "pre-formatted",
          "content": [
            {
              "type": "heading",
              "style": "Heading 1",
              "data": { "text": "Executive Summary" }
            },
            {
              "type": "paragraph",
              "data": {
                "runs": [
                  { "text": "Revenue increased by ", "bold": false },
                  { "text": "23%", "bold": true, "color": "00AA00" }
                ]
              }
            }
          ]
        }
      },
      "meta_data": {
        "label": "Quarterly Report",
        "section": "analytics"
      }
    },
    {
      "type": "url",
      "document_url": "https://storage.example.com/terms-and-conditions.pdf",
      "meta_data": {
        "label": "Terms & Conditions",
        "section": "legal"
      }
    }
  ],
  "output_filename": "complete-package-2025-001",
  "webhook": "https://yourapp.com/webhooks/process-merge",
  "file_upload_url": "https://s3.amazonaws.com/presigned-upload-url",
  "meta_data": {
    "project": "Q3-2025",
    "client": "Acme Corp",
    "category": "financial-package"
  }
}
```

**Document Types:**

1. **`type: "url"`** - Download existing document

   - `document_url` (required): URL to download document from
   - `meta_data` (optional): Document-level metadata

2. **`type: "generate"`** - Generate PDF from template

   - `mode` (required): `"static"` or `"dynamic"`
   - `template_url`:
     - **Static mode**: Required - URL to Word template
     - **Dynamic mode**: Required unless `use_empty_template` is true
   - `template_hash` (optional): Hash for template caching (reduces download time on repeated use)
   - `use_empty_template` (optional, boolean, default: false): Only for dynamic mode. If true, starts with an empty .docx file instead of downloading a template
   - `data` (required): JSON data for template
   - `output_filename` (optional): Filename for dynamic mode
   - `meta_data` (optional): Document-level metadata

   **Note**: Static mode always requires a template URL. Dynamic mode can optionally use `use_empty_template: true` to generate PDFs from scratch without a template.

**Supported File Formats (for type="url"):**

- **PDFs**: `.pdf` (direct merge)
- **Images**: `.png`, `.jpg`, `.jpeg`, `.gif`, `.bmp`, `.tiff`, `.svg` (converted to PDF)

**Response (200 OK):**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440003",
  "client_job_id": "PROC-2025-001",
  "task_id": "p1q2r3s4-t5u6-v7w8-x9y0-z1a2b3c4d5e6",
  "status": "queued",
  "started_at": "2025-10-09T10:00:00Z",
  "meta_data": {
    "project": "Q3-2025",
    "client": "Acme Corp",
    "category": "financial-package"
  }
}
```

### Check Process and Merge Status

```http
GET /api/v1/process-and-merge-pdfs/status?job_id=PROC-2025-001
Authorization: Bearer <token>
```

**Query Parameters:**

- `job_id` (required): The job UUID (primary key) to check status for. This UUID is returned in the `job_id` field when creating a job.

**Response (Running):**

```json
{
  "client_job_id": "PROC-2025-001",
  "task_id": "p1q2r3s4-t5u6-v7w8-x9y0-z1a2b3c4d5e6",
  "status": "processing",
  "started_at": "2025-10-09T10:00:00Z",
  "ended_at": null,
  "processing_time": null,
  "progress": 50,
  "documents": [
    {
      "type": "url",
      "status": "completed",
      "processing_time": 2.1,
      "meta_data": { "label": "Cover Page" }
    },
    {
      "type": "generate",
      "status": "completed",
      "processing_time": 5.3,
      "meta_data": { "label": "Invoice" }
    },
    {
      "type": "generate",
      "status": "processing",
      "meta_data": { "label": "Quarterly Report" }
    },
    {
      "type": "url",
      "status": "queued",
      "meta_data": { "label": "Terms & Conditions" }
    }
  ],
  "meta_data": {
    "project": "Q3-2025",
    "client": "Acme Corp"
  },
  "download_url": null
}
```

**Response (Completed):**

```json
{
  "client_job_id": "PROC-2025-001",
  "task_id": "p1q2r3s4-t5u6-v7w8-x9y0-z1a2b3c4d5e6",
  "status": "completed",
  "started_at": "2025-10-09T10:00:00Z",
  "ended_at": "2025-10-09T10:00:25Z",
  "processing_time": "25.4",
  "progress": 100,
  "documents": [
    {
      "type": "url",
      "status": "completed",
      "processing_time": 2.1,
      "meta_data": { "label": "Cover Page" }
    },
    {
      "type": "generate",
      "status": "completed",
      "processing_time": 5.3,
      "meta_data": { "label": "Invoice" }
    },
    {
      "type": "generate",
      "status": "completed",
      "processing_time": 10.2,
      "meta_data": { "label": "Quarterly Report" }
    },
    {
      "type": "url",
      "status": "completed",
      "processing_time": 2.0,
      "meta_data": { "label": "Terms & Conditions" }
    }
  ],
  "meta_data": {
    "project": "Q3-2025",
    "client": "Acme Corp"
  },
  "download_url": "https://s3.amazonaws.com/bucket/pdfs/merged/PROC-2025-001.pdf?..."
}
```

**Response (Completed with Partial Failure):**

When some documents fail but at least one succeeds, the job completes with status "partial_completed" and failed documents are indicated:

```json
{
  "client_job_id": "PROC-2025-001",
  "task_id": "p1q2r3s4-t5u6-v7w8-x9y0-z1a2b3c4d5e6",
  "status": "partial_completed",
  "started_at": "2025-10-09T10:00:00Z",
  "ended_at": "2025-10-09T10:00:25Z",
  "processing_time": "25.4",
  "progress": 90,
  "documents": [
    {
      "type": "url",
      "status": "completed",
      "processing_time": 2.1,
      "meta_data": { "label": "Cover Page" }
    },
    {
      "type": "generate",
      "status": "failed",
      "processing_time": 1.2,
      "error": "Failed to download template: 404 Not Found",
      "meta_data": { "label": "Invoice" }
    },
    {
      "type": "generate",
      "status": "completed",
      "processing_time": 10.2,
      "meta_data": { "label": "Quarterly Report" }
    },
    {
      "type": "url",
      "status": "completed",
      "processing_time": 2.0,
      "meta_data": { "label": "Terms & Conditions" }
    }
  ],
  "meta_data": {
    "project": "Q3-2025",
    "client": "Acme Corp"
  },
  "download_url": "https://s3.amazonaws.com/bucket/pdfs/merged/PROC-2025-001.pdf?...",
  "error": "1 document(s) failed to process"
}
```

**Response (Failed):**

When all documents fail or merging fails:

```json
{
  "client_job_id": "PROC-2025-001",
  "task_id": "p1q2r3s4-t5u6-v7w8-x9y0-z1a2b3c4d5e6",
  "status": "failed",
  "started_at": "2025-10-09T10:00:00Z",
  "ended_at": "2025-10-09T10:00:05Z",
  "processing_time": "5.2",
  "progress": 90,
  "documents": [
    {
      "type": "url",
      "status": "failed",
      "error": "Failed to download: 404 Not Found",
      "meta_data": { "label": "Cover Page" }
    },
    {
      "type": "generate",
      "status": "failed",
      "error": "Failed to download template: 404 Not Found",
      "meta_data": { "label": "Invoice" }
    }
  ],
  "meta_data": {
    "project": "Q3-2025",
    "client": "Acme Corp"
  },
  "download_url": null,
  "error": "All documents failed to process"
}
```

**Error Responses:**

```json
{
  "status": "Bad Request",
  "error": {
    "message": "client_job_id is required"
  }
}
```

```json
{
  "status": "Bad Request",
  "error": {
    "message": "documents array is required and must not be empty"
  }
}
```

```json
{
  "status": "Bad Request",
  "error": {
    "message": "Document at index 1: 'template_url' is required for type='generate'"
  }
}
```

```json
{
  "status": "Not Found",
  "error": {
    "message": "Job PROC-2025-001 not found"
  }
}
```

**Progress Tracking:**

The progress percentage is calculated as:

- **0-90%**: Document processing phase (proportional to completed documents)
- **90-100%**: Merging phase
- **100%**: Job completed successfully

**Webhook Notifications:**

Real-time webhook notifications are sent at:

1. Job started (progress: 0%)
2. After each document completes (progress updates incrementally)
3. During merge operation (progress: 90%)
4. Job completed or failed (progress: 100% or final state)

See [WEBHOOKS.md](WEBHOOKS.md) for webhook payload format and signature verification.

---

## Process and ZIP

### Process and ZIP

**Advanced Operation**: Generate PDFs from templates AND/OR download existing documents, then package them all into a ZIP archive in one atomic operation.

Similar to Process and Merge, but creates a ZIP archive instead of merging into a single PDF. Perfect for creating document packages where files need to remain separate.

```http
POST /api/v1/process-and-zip
Authorization: Bearer <token>
Content-Type: application/json
```

**Request Body:**

```json
{
  "client_job_id": "PROC-ZIP-001",
  "documents": [
    {
      "type": "url",
      "document_url": "https://storage.example.com/cover-page.pdf",
      "meta_data": {
        "label": "Cover Page",
        "section": "front-matter"
      }
    },
    {
      "type": "generate",
      "mode": "static",
      "template_url": "https://storage.example.com/invoice-template.docx",
      "template_hash": "abc123def456",
      "data": {
        "invoice_number": "INV-2025-001",
        "date": "2025-10-10",
        "customer_name": "Acme Corp",
        "total": 1250.0
      },
      "meta_data": {
        "label": "Invoice",
        "section": "billing"
      }
    },
    {
      "type": "generate",
      "mode": "dynamic",
      "template_url": "https://storage.example.com/report-template.docx",
      "template_hash": "xyz789ghi012",
      "output_filename": "quarterly_report",
      "data": {
        "report_title": "Q3 2025 Report",
        "report_body": {
          "data-type": "pre-formatted",
          "content": [
            {
              "type": "heading",
              "style": "Heading 1",
              "data": { "text": "Executive Summary" }
            },
            {
              "type": "paragraph",
              "data": {
                "runs": [
                  { "text": "Revenue increased by ", "bold": false },
                  { "text": "23%", "bold": true, "color": "00AA00" }
                ]
              }
            }
          ]
        }
      },
      "meta_data": {
        "label": "Quarterly Report",
        "section": "analytics"
      }
    },
    {
      "type": "url",
      "document_url": "https://storage.example.com/terms-and-conditions.pdf",
      "meta_data": {
        "label": "Terms & Conditions",
        "section": "legal"
      }
    }
  ],
  "output_filename": "complete-package-2025-001",
  "webhook": "https://yourapp.com/webhooks/process-zip",
  "file_upload_url": "https://s3.amazonaws.com/presigned-upload-url",
  "meta_data": {
    "project": "Q3-2025",
    "client": "Acme Corp",
    "category": "document-package"
  }
}
```

**Document Types:**

1. **`type: "url"`** - Download existing document

   - `document_url` (required): URL to download document from
   - `meta_data` (optional): Document-level metadata

2. **`type: "generate"`** - Generate PDF from template

   - `mode` (required): `"static"` or `"dynamic"`
   - `template_url`:
     - **Static mode**: Required - URL to Word template
     - **Dynamic mode**: Required unless `use_empty_template` is true
   - `template_hash` (optional): Hash for template caching (reduces download time on repeated use)
   - `use_empty_template` (optional, boolean, default: false): Only for dynamic mode. If true, starts with an empty .docx file instead of downloading a template
   - `data` (required): JSON data for template
   - `output_filename` (optional): Filename for dynamic mode
   - `meta_data` (optional): Document-level metadata

   **Note**: Static mode always requires a template URL. Dynamic mode can optionally use `use_empty_template: true` to generate PDFs from scratch without a template.

**Response (200 OK):**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440004",
  "client_job_id": "PROC-ZIP-001",
  "task_id": "x1y2z3a4-b5c6-d7e8-f9g0-h1i2j3k4l5m6",
  "status": "queued",
  "started_at": "2025-10-10T10:00:00Z",
  "meta_data": {
    "project": "Q3-2025",
    "client": "Acme Corp",
    "category": "document-package"
  }
}
```

### Check Process and ZIP Status

```http
GET /api/v1/process-and-zip/status?job_id=PROC-ZIP-001
Authorization: Bearer <token>
```

**Query Parameters:**

- `job_id` (required): The job UUID (primary key) to check status for. This UUID is returned in the `job_id` field when creating a job.

**Response (Running):**

```json
{
  "client_job_id": "PROC-ZIP-001",
  "task_id": "x1y2z3a4-b5c6-d7e8-f9g0-h1i2j3k4l5m6",
  "status": "processing",
  "started_at": "2025-10-10T10:00:00Z",
  "ended_at": null,
  "processing_time": null,
  "progress": 50,
  "documents": [
    {
      "type": "url",
      "status": "completed",
      "processing_time": 2.1,
      "meta_data": { "label": "Cover Page" }
    },
    {
      "type": "generate",
      "status": "completed",
      "processing_time": 5.3,
      "meta_data": { "label": "Invoice" }
    },
    {
      "type": "generate",
      "status": "processing",
      "meta_data": { "label": "Quarterly Report" }
    },
    {
      "type": "url",
      "status": "queued",
      "meta_data": { "label": "Terms & Conditions" }
    }
  ],
  "meta_data": {
    "project": "Q3-2025",
    "client": "Acme Corp"
  },
  "download_url": null
}
```

**Note:** Document objects in the status response include only: `type`, `status`, `processing_time` (if not null), `error` (if present), and `meta_data`. Timing fields like `started_at`, `ended_at`, `mode`, `template_url`, and `data` are intentionally filtered out for security and clarity.

**Response (Completed):**

```json
{
  "client_job_id": "PROC-ZIP-001",
  "task_id": "x1y2z3a4-b5c6-d7e8-f9g0-h1i2j3k4l5m6",
  "status": "completed",
  "started_at": "2025-10-10T10:00:00Z",
  "ended_at": "2025-10-10T10:00:25Z",
  "processing_time": "25.4",
  "progress": 100,
  "documents": [
    {
      "type": "url",
      "status": "completed",
      "processing_time": 2.1,
      "meta_data": { "label": "Cover Page" }
    },
    {
      "type": "generate",
      "status": "completed",
      "processing_time": 5.3,
      "meta_data": { "label": "Invoice" }
    },
    {
      "type": "generate",
      "status": "completed",
      "processing_time": 10.2,
      "meta_data": { "label": "Quarterly Report" }
    },
    {
      "type": "url",
      "status": "completed",
      "processing_time": 2.0,
      "meta_data": { "label": "Terms & Conditions" }
    }
  ],
  "meta_data": {
    "project": "Q3-2025",
    "client": "Acme Corp"
  },
  "download_url": "https://s3.amazonaws.com/bucket/zips/processed/PROC-ZIP-001.zip?..."
}
```

**Progress Tracking:**

The progress percentage is calculated as:

- **0-90%**: Document processing phase (proportional to completed documents)
- **90-100%**: ZIP creation phase
- **100%**: Job completed successfully

**Duplicate Filename Handling:**

When multiple files have the same filename (e.g., generated PDFs with the same output_filename or downloaded files with identical names), they are automatically renamed with numeric suffixes to prevent overwriting:
- First file: `report.pdf`
- Second file: `report_1.pdf`
- Third file: `report_2.pdf`

**Webhook Notifications:**

Real-time webhook notifications are sent at:

1. Job started (progress: 0%)
2. After each document completes (progress updates incrementally)
3. During ZIP operation (progress: 90%)
4. Job completed or failed (progress: 100% or final state)

See [WEBHOOKS.md](WEBHOOKS.md) for webhook payload format and signature verification.

---

## ZIP Archive Creation

### Create ZIP Archive

Create a ZIP archive from multiple files of any type.

```http
POST /api/v1/create-zip
Authorization: Bearer <token>
Content-Type: application/json
```

**Request Body:**

```json
{
  "client_job_id": "ZIP-2025-001",
  "document_urls": [
    "https://storage.example.com/report.pdf",
    "https://storage.example.com/data.xlsx",
    "https://storage.example.com/presentation.pptx",
    "https://storage.example.com/image.jpg",
    "https://storage.example.com/document.docx"
  ],
  "output_filename": "project-files",
  "webhook": "https://yourapp.com/webhooks/zip-creation",
  "file_upload_url": "https://s3.amazonaws.com/presigned-upload-url",
  "meta_data": {
    "project": "Q4-2025",
    "department": "Engineering"
  }
}
```

**Supported File Types:**

- **Any file type** - No format restrictions!
- PDFs, images, documents, spreadsheets, presentations, videos, audio, code files, etc.
- Files are stored flat in the ZIP (no directory structure)

**Duplicate Filename Handling:**

When multiple files have the same filename, they are automatically renamed with numeric suffixes to prevent overwriting:
- First file: `document.pdf`
- Second file: `document_1.pdf`
- Third file: `document_2.pdf`

**Response (200 OK):**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440005",
  "client_job_id": "ZIP-2025-001",
  "task_id": "z1a2b3c4-d5e6-f7g8-h9i0-j1k2l3m4n5o6",
  "status": "queued",
  "started_at": "2025-10-07T10:15:30Z",
  "meta_data": {
    "project": "Q4-2025",
    "department": "Engineering"
  }
}
```

### Check ZIP Status

```http
GET /api/v1/create-zip/status?job_id=ZIP-2025-001
Authorization: Bearer <token>
```

**Response (Queued):**

```json
{
  "client_job_id": "ZIP-2025-001",
  "task_id": "z1a2b3c4-d5e6-f7g8-h9i0-j1k2l3m4n5o6",
  "status": "queued",
  "started_at": "2025-10-07T10:15:30Z",
  "ended_at": null,
  "processing_time": null,
  "meta_data": {
    "project": "Q4-2025",
    "department": "Engineering"
  },
  "download_url": null,
  "documents": [
    {
      "type": "url",
      "document_url": "https://storage.example.com/report.pdf",
      "status": "queued"
    },
    {
      "type": "url",
      "document_url": "https://storage.example.com/data.xlsx",
      "status": "queued"
    },
    {
      "type": "url",
      "document_url": "https://storage.example.com/presentation.pptx",
      "status": "queued"
    },
    {
      "type": "url",
      "document_url": "https://storage.example.com/image.jpg",
      "status": "queued"
    },
    {
      "type": "url",
      "document_url": "https://storage.example.com/document.docx",
      "status": "queued"
    }
  ]
}
```

**Response (Completed):**

```json
{
  "client_job_id": "ZIP-2025-001",
  "task_id": "z1a2b3c4-d5e6-f7g8-h9i0-j1k2l3m4n5o6",
  "status": "completed",
  "started_at": "2025-10-07T10:15:30Z",
  "ended_at": "2025-10-07T10:15:42Z",
  "processing_time": "12.3",
  "meta_data": {
    "project": "Q4-2025",
    "department": "Engineering"
  },
  "download_url": "https://s3.amazonaws.com/bucket/zips/ZIP-2025-001.zip?...",
  "documents": [
    {
      "type": "url",
      "document_url": "https://storage.example.com/report.pdf",
      "status": "completed",
      "processing_time": 2.1
    },
    {
      "type": "url",
      "document_url": "https://storage.example.com/data.xlsx",
      "status": "completed",
      "processing_time": 1.5
    },
    {
      "type": "url",
      "document_url": "https://storage.example.com/presentation.pptx",
      "status": "completed",
      "processing_time": 3.2
    },
    {
      "type": "url",
      "document_url": "https://storage.example.com/image.jpg",
      "status": "completed",
      "processing_time": 0.8
    },
    {
      "type": "url",
      "document_url": "https://storage.example.com/document.docx",
      "status": "completed",
      "processing_time": 2.4
    }
  ]
}
```

**Response (Failed):**

```json
{
  "client_job_id": "ZIP-2025-001",
  "task_id": "z1a2b3c4-d5e6-f7g8-h9i0-j1k2l3m4n5o6",
  "status": "failed",
  "started_at": "2025-10-07T10:15:30Z",
  "ended_at": "2025-10-07T10:15:33Z",
  "processing_time": "3.1",
  "meta_data": {
    "project": "Q4-2025",
    "department": "Engineering"
  },
  "download_url": null,
  "error": "Failed to download file from https://storage.example.com/data.xlsx: 404 Not Found",
  "documents": [
    {
      "type": "url",
      "document_url": "https://storage.example.com/report.pdf",
      "status": "completed",
      "processing_time": 1.8
    },
    {
      "type": "url",
      "document_url": "https://storage.example.com/data.xlsx",
      "status": "failed",
      "error": "Failed to download file: 404 Not Found"
    },
    {
      "type": "url",
      "document_url": "https://storage.example.com/presentation.pptx",
      "status": "queued"
    },
    {
      "type": "url",
      "document_url": "https://storage.example.com/image.jpg",
      "status": "queued"
    },
    {
      "type": "url",
      "document_url": "https://storage.example.com/document.docx",
      "status": "queued"
    }
  ]
}
```

---

## PDF Splitting

### Split PDF

Split a PDF into multiple files by page numbers or logical labels.

```http
POST /api/v1/split-pdf
Authorization: Bearer <token>
Content-Type: application/json
```

**Request Body (Split by Pages):**

```json
{
  "client_job_id": "SPLIT-CONTRACT-2025-001",
  "document_url": "https://storage.example.com/contract.pdf",
  "webhook": "https://yourapp.com/webhooks/pdf-split",
  "meta_data": {
    "contract_id": "CNT-2025-001",
    "client": "Acme Corp"
  },
  "splits": [
    {
      "output_filename": "cover_page",
      "pages": [1],
      "meta_data": { "section": "cover" }
    },
    {
      "output_filename": "terms_and_conditions",
      "pages": [2, 3, 4, 5],
      "file_upload_url": "https://s3.amazonaws.com/presigned-upload-url-1",
      "meta_data": { "section": "terms" }
    },
    {
      "output_filename": "appendix",
      "pages": [6, 7, 8],
      "meta_data": { "section": "appendix" }
    }
  ]
}
```

**Request Body (Split by Labels):**

```json
{
  "client_job_id": "SPLIT-BOOK-2025-001",
  "document_url": "https://storage.example.com/book.pdf",
  "splits": [
    {
      "output_filename": "front_matter",
      "labels": ["i", "ii", "iii", "iv"]
    },
    {
      "output_filename": "chapter_one",
      "labels": ["1", "2", "3"]
    }
  ]
}
```

**Response (200 OK):**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440006",
  "client_job_id": "SPLIT-CONTRACT-2025-001",
  "task_id": "a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6",
  "status": "queued",
  "started_at": "2025-10-03T10:15:30Z",
  "meta_data": {
    "contract_id": "CNT-2025-001",
    "client": "Acme Corp"
  },
  "splits": []
}
```

### Check Split Status

```http
GET /api/v1/split-pdf/status?job_id=SPLIT-CONTRACT-2025-001
Authorization: Bearer <token>
```

**Response (Completed):**

```json
{
  "client_job_id": "SPLIT-CONTRACT-2025-001",
  "task_id": "a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6",
  "status": "completed",
  "started_at": "2025-10-03T10:15:30Z",
  "ended_at": "2025-10-03T10:15:45Z",
  "processing_time": "15.2",
  "progress": 100,
  "meta_data": {
    "contract_id": "CNT-2025-001",
    "client": "Acme Corp"
  },
  "documents": [
    {
      "type": "url",
      "document_url": "https://storage.example.com/contract.pdf",
      "status": "completed"
    }
  ],
  "splits": [
    {
      "output_filename": "cover_page",
      "pages": [1],
      "labels": null,
      "status": "completed",
      "status_remark": "Completed",
      "download_url": "https://s3.amazonaws.com/bucket/splits/...",
      "file_size": 245678,
      "processing_time": 1.2,
      "meta_data": { "section": "cover" }
    },
    {
      "output_filename": "terms_and_conditions",
      "pages": [2, 3, 4, 5],
      "labels": null,
      "status": "completed",
      "status_remark": "Completed",
      "download_url": "https://s3.amazonaws.com/presigned-upload-url-1",
      "file_size": 1245678,
      "processing_time": 3.5,
      "meta_data": { "section": "terms" }
    },
    {
      "output_filename": "appendix",
      "pages": [6, 7, 8],
      "labels": null,
      "status": "completed",
      "status_remark": "Completed",
      "download_url": "https://s3.amazonaws.com/bucket/splits/...",
      "file_size": 892341,
      "processing_time": 2.1,
      "meta_data": { "section": "appendix" }
    }
  ]
}
```

---

## Webhook Management

### Regenerate Webhook Secret

```http
POST /api/v1/webhook/regenerate-secret
Authorization: Bearer <token>
```

**Response (200 OK):**

```json
{
  "message": "Webhook secret regenerated successfully",
  "webhook_secret": "new_secret_a1b2c3d4e5f6g7h8...",
  "created_at": "2025-10-03T10:20:00Z",
  "previous_secret": "****...xyz",
  "warning": "⚠️ Save this secret securely - it won't be shown again!"
}
```

### Get Secret Info

```http
GET /api/v1/webhook/secret-info
Authorization: Bearer <token>
```

**Response (200 OK):**

```json
{
  "has_secret": true,
  "webhook_secret": "****...xyz",
  "created_at": "2025-10-03T10:20:00Z",
  "help": "Use POST /api/v1/webhook/regenerate-secret to generate a new secret"
}
```

### Test Webhook

```http
POST /api/v1/webhook/test
Authorization: Bearer <token>
Content-Type: application/json
```

**Request Body:**

```json
{
  "webhook_url": "https://yourapp.com/webhooks/test"
}
```

**Response (200 OK):**

```json
{
  "message": "Test webhook sent successfully",
  "webhook_url": "https://yourapp.com/webhooks/test",
  "result": {
    "success": true,
    "response_text": "OK"
  }
}
```

---

## Logs & Monitoring

### Get Job Logs

Retrieve job logs with optional filtering and detailed request data.

```http
GET /api/v1/logs?limit=50&offset=0&status=completed&client_job_id=INV-2025-001
Authorization: Bearer <token>
```

**Query Parameters:**

- `limit` (int, optional): Number of records to return (default: 100, max: 1000)
- `offset` (int, optional): Number of records to skip for pagination (default: 0)
- `status` (string, optional): Filter by status (queued, processing, completed, failed, partial_completed)
- `client_job_id` (string, optional): Filter by specific client_job_id
- `job_type` (string, optional): Filter by job type (generate, split, merge, zip, process_and_merge, process_and_zip)
- `include_request_data` (boolean, optional): Include full original request data from S3 (default: false)

**Response (200 OK) - Basic:**

```json
{
  "total": 50,
  "offset": 0,
  "limit": 50,
  "logs": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "client_job_id": "INV-2025-001",
      "task_id": "e3f2a1b5-4c3d-2e1f-0a9b-8c7d6e5f4a3b",
      "job_type": "generate",
      "status": "completed",
      "download_url": "https://s3.amazonaws.com/bucket/pdfs/INV-2025-001.pdf?...",
      "processing_time": 2.3,
      "created_at": "2025-10-03T10:00:00Z",
      "started_at": "2025-10-03T10:00:00Z",
      "updated_at": "2025-10-03T10:00:02Z",
      "ended_at": "2025-10-03T10:00:02Z",
      "meta_data": {
        "customer_id": "12345",
        "department": "sales"
      },
      "request_audit_s3_key": "request_audit/550e8400-e29b-41d4-a716-446655440000.json",
      "documents": [
        {
          "type": "generate",
          "mode": "static",
          "status": "completed"
        }
      ]
    }
  ]
}
```

**Response (200 OK) - With Request Data:**

When `include_request_data=true` is specified, the full original API request is fetched from S3 and included:

```http
GET /api/v1/logs?limit=10&include_request_data=true&job_type=merge
Authorization: Bearer <token>
```

```json
{
  "total": 10,
  "offset": 0,
  "limit": 10,
  "logs": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440001",
      "client_job_id": "MERGE-2025-001",
      "task_id": "m1n2o3p4-q5r6-s7t8-u9v0-w1x2y3z4a5b6",
      "job_type": "merge",
      "status": "completed",
      "download_url": "https://s3.amazonaws.com/bucket/pdfs/merged/MERGE-2025-001.pdf?...",
      "processing_time": 15.2,
      "created_at": "2025-10-07T10:15:30Z",
      "started_at": "2025-10-07T10:15:30Z",
      "updated_at": "2025-10-07T10:15:45Z",
      "ended_at": "2025-10-07T10:15:45Z",
      "meta_data": {
        "project": "Q4-2025",
        "category": "reports"
      },
      "request_audit_s3_key": "request_audit/550e8400-e29b-41d4-a716-446655440001.json",
      "documents": [
        {
          "type": "url",
          "status": "completed",
          "processing_time": 2.1
        },
        {
          "type": "url",
          "status": "completed",
          "processing_time": 1.8
        }
      ],
      "request_data": {
        "client_job_id": "MERGE-2025-001",
        "document_urls": [
          "https://storage.example.com/cover.pdf",
          "https://storage.example.com/logo.png",
          "https://storage.example.com/content.pdf"
        ],
        "output_filename": "merged-document",
        "webhook": "https://yourapp.com/webhooks/pdf-merge",
        "file_upload_url": "https://s3.amazonaws.com/presigned-upload-url",
        "meta_data": {
          "project": "Q4-2025",
          "category": "reports"
        }
      }
    }
  ]
}
```

**Notes:**

- **Performance**: Setting `include_request_data=true` will fetch data from S3 for each log entry, which may slow down the response for large result sets. Use this parameter only when you need the full request details.
- **Audit Compliance**: The `request_data` field contains the complete original API request including all URLs, template data, and document configurations that were submitted when the job was created.
- **Storage**: Request audit data is stored in S3 with a lifecycle policy (typically 90 days retention).
- **Error Handling**: If request data cannot be retrieved from S3, the `request_data` field will be `null` and a `request_data_error` field will be included with the error message.

---

## Error Handling

### HTTP Status Codes

| Code | Meaning               | Description                       |
| ---- | --------------------- | --------------------------------- |
| 200  | OK                    | Request successful                |
| 201  | Created               | Resource created successfully     |
| 202  | Accepted              | Request accepted for processing   |
| 400  | Bad Request           | Invalid request parameters        |
| 401  | Unauthorized          | Missing or invalid authentication |
| 404  | Not Found             | Resource not found                |
| 409  | Conflict              | Resource already exists           |
| 500  | Internal Server Error | Server error occurred             |

### Error Response Format

```json
{
  "status": "Bad Request",
  "error": {
    "message": "client_job_id is required",
    "field": "client_job_id",
    "type": "validation_error"
  }
}
```

### Common Errors

**Missing Authentication:**

```json
{
  "error": "Token is missing"
}
```

**Invalid Token:**

```json
{
  "error": "Token is invalid or expired"
}
```

**Validation Error:**

```json
{
  "status": "Bad Request",
  "error": {
    "message": "Split 'file-1' must have either 'pages' or 'labels'"
  }
}
```

---

## Rate Limits

**Current Limits** (per user):

- API requests: 1000/hour
- PDF generation: 100/hour
- PDF splitting: 50/hour

**Rate Limit Headers:**

```http
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 847
X-RateLimit-Reset: 1633024800
```

**Rate Limit Exceeded Response (429):**

```json
{
  "error": "Rate limit exceeded",
  "retry_after": 3600
}
```

---

## Webhooks

Webhooks are sent for async operations (PDF generation, splitting).

See [WEBHOOKS.md](WEBHOOKS.md) for detailed webhook documentation including:

- Webhook payload format
- HMAC signature verification
- Example implementations (Python, Node.js)

---
