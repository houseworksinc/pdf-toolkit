# Webhook System

Complete guide to implementing and securing webhooks with HouseWorks PDF Toolkit.

---

## Table of Contents

- [Overview](#overview)
- [Webhook Secrets](#webhook-secrets)
- [Payload Format](#payload-format)
- [Security &amp; Verification](#security--verification)
- [Implementation Examples](#implementation-examples)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

---

## Overview

Webhooks provide real-time notifications about async job status. They are sent for:

- **PDF Generation Jobs**: Success/failure notifications
- **PDF Merging Jobs**: Success/failure notifications
- **ZIP Archive Creation**: Success/failure notifications
- **PDF Splitting Jobs**: Progress updates per split + final status
- **Process and Merge Jobs**: Real-time progress updates per document + final status

### Key Features

- **HMAC-SHA256 Signatures**: Every webhook is cryptographically signed
- **Automatic Retries**: 3 retry attempts with exponential backoff (1s, 2s, 4s)
- **Progress Tracking**: Real-time progress percentage for split jobs
- **Flexible Delivery**: Send to any HTTPS endpoint

---

## Webhook Secrets

### Getting Your Secret

**On Registration:**

```json
{
  "webhook_secret": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6...",
  "warning": "⚠️ Save this secret securely - it won't be shown again!"
}
```

⚠️ **Store securely!** This secret is shown only once.

### Regenerating Secrets

```bash
curl -X POST https://api.houseworks.com/api/v1/webhook/regenerate-secret \
  -H "Authorization: Bearer <your_jwt_token>"
```

**When to regenerate:**

- Secret compromised
- Regular rotation (recommended: every 90 days)
- Team member departure

### Checking Secret Status

```bash
curl https://api.houseworks.com/api/v1/webhook/secret-info \
  -H "Authorization: Bearer <your_jwt_token>"
```

Response:

```json
{
  "has_secret": true,
  "webhook_secret": "****...xyz", // Last 4 chars
  "created_at": "2025-10-03T10:00:00Z"
}
```

---

## Payload Format

### Common Headers

Every webhook request includes:

```http
POST /your-webhook-endpoint
Content-Type: application/json
X-Webhook-Signature: sha256=a1b2c3d4e5f6g7h8i9j0...
X-Webhook-Timestamp: 1633024800
X-Job-ID: SPLIT-CONTRACT-2025-001
User-Agent: PDF-Toolkit-Webhook/1.0
```

### PDF Generation Webhook

**Status: Success**

```json
{
  "client_job_id": "INV-2025-001",
  "task_id": "e3f2a1b5-4c3d-2e1f-0a9b-8c7d6e5f4a3b",
  "status": "completed",
  "started_at": "2025-10-03T10:00:00Z",
  "ended_at": "2025-10-03T10:00:02Z",
  "processing_time": "2.3",
  "download_url": "https://s3.amazonaws.com/...",
  "meta_data": {},
  "documents": [
    {
      "type": "generate",
      "status": "completed",
      "processing_time": 2.3,
      "meta_data": {}
    }
  ]
}
```

**Status: Failed**

```json
{
  "client_job_id": "INV-2025-001",
  "task_id": "e3f2a1b5-4c3d-2e1f-0a9b-8c7d6e5f4a3b",
  "status": "failed",
  "started_at": "2025-10-03T10:00:00Z",
  "ended_at": "2025-10-03T10:00:05Z",
  "error": "Template file could not be downloaded",
  "meta_data": {},
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

### PDF Merging Webhook

**Status: Success**

```json
{
  "client_job_id": "MERGE-2025-001",
  "task_id": "m1n2o3p4-q5r6-s7t8-u9v0-w1x2y3z4a5b6",
  "status": "completed",
  "started_at": "2025-10-07T10:15:30Z",
  "ended_at": "2025-10-07T10:15:45Z",
  "processing_time": "15.2",
  "download_url": "https://s3.amazonaws.com/bucket/pdfs/merged/MERGE-2025-001.pdf?...",
  "meta_data": {
    "project": "Q4-2025",
    "category": "reports"
  },
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
    }
  ]
}
```

**Status: Failed**

```json
{
  "client_job_id": "MERGE-2025-001",
  "task_id": "m1n2o3p4-q5r6-s7t8-u9v0-w1x2y3z4a5b6",
  "status": "failed",
  "started_at": "2025-10-07T10:15:30Z",
  "ended_at": "2025-10-07T10:15:32Z",
  "processing_time": "2.1",
  "error": "Failed to download file from https://storage.example.com/content.pdf: 404 Not Found",
  "meta_data": {
    "project": "Q4-2025",
    "category": "reports"
  },
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
    }
  ]
}
```

### ZIP Archive Creation Webhook

**Status: Success**

```json
{
  "client_job_id": "ZIP-2025-001",
  "task_id": "z1a2b3c4-d5e6-f7g8-h9i0-j1k2l3m4n5o6",
  "status": "completed",
  "started_at": "2025-10-07T10:15:30Z",
  "ended_at": "2025-10-07T10:15:42Z",
  "processing_time": "12.3",
  "download_url": "https://s3.amazonaws.com/bucket/zips/ZIP-2025-001.zip?...",
  "meta_data": {
    "project": "Q4-2025",
    "department": "Engineering"
  },
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
    }
  ]
}
```

**Status: Failed**

```json
{
  "client_job_id": "ZIP-2025-001",
  "task_id": "z1a2b3c4-d5e6-f7g8-h9i0-j1k2l3m4n5o6",
  "status": "failed",
  "started_at": "2025-10-07T10:15:30Z",
  "ended_at": "2025-10-07T10:15:33Z",
  "processing_time": "3.1",
  "error": "Failed to download file from https://storage.example.com/data.xlsx: 404 Not Found",
  "meta_data": {
    "project": "Q4-2025",
    "department": "Engineering"
  },
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
    }
  ]
}
```

### Process and Merge PDFs Webhook

This webhook is sent when a process-and-merge job completes. It includes additional fields for tracking document processing statistics.

**Status: Completed**

```json
{
  "client_job_id": "PROC-2025-001",
  "task_id": "p1q2r3s4-t5u6-v7w8-x9y0-z1a2b3c4d5e6",
  "status": "completed",
  "started_at": "2025-10-09T10:00:00Z",
  "ended_at": "2025-10-09T10:00:25Z",
  "processing_time": "25.40",
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
    }
  ],
  "meta_data": {
    "project": "Q3-2025",
    "client": "Acme Corp"
  },
  "download_url": "https://s3.amazonaws.com/bucket/pdfs/merged/PROC-2025-001.pdf?...",
  "documents_completed": 3,
  "documents_failed": 0
}
```

**Status: Partial Success**

When some documents fail but at least one succeeds:

```json
{
  "client_job_id": "PROC-2025-001",
  "task_id": "p1q2r3s4-t5u6-v7w8-x9y0-z1a2b3c4d5e6",
  "status": "partial_completed",
  "started_at": "2025-10-09T10:00:00Z",
  "ended_at": "2025-10-09T10:00:25Z",
  "processing_time": "25.40",
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
    }
  ],
  "meta_data": {
    "project": "Q3-2025",
    "client": "Acme Corp"
  },
  "download_url": "https://s3.amazonaws.com/bucket/pdfs/merged/PROC-2025-001.pdf?...",
  "error": "1 document(s) failed to process",
  "documents_completed": 2,
  "documents_failed": 1
}
```

**Status: Failed**

```json
{
  "client_job_id": "PROC-2025-001",
  "task_id": "p1q2r3s4-t5u6-v7w8-x9y0-z1a2b3c4d5e6",
  "status": "failed",
  "started_at": "2025-10-09T10:00:00Z",
  "ended_at": "2025-10-09T10:00:05Z",
  "processing_time": "5.20",
  "progress": 100,
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
  "error": "All documents failed to process",
  "documents_completed": 0,
  "documents_failed": 2
}
```

### Process and ZIP Webhook

This webhook is sent when a process-and-zip job completes. Similar to Process and Merge, it includes document processing statistics.

**Status: Completed**

```json
{
  "client_job_id": "PROC-ZIP-001",
  "task_id": "x1y2z3a4-b5c6-d7e8-f9g0-h1i2j3k4l5m6",
  "status": "completed",
  "started_at": "2025-10-10T10:00:00Z",
  "ended_at": "2025-10-10T10:00:25Z",
  "processing_time": "25.40",
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
    }
  ],
  "meta_data": {
    "project": "Q3-2025",
    "client": "Acme Corp"
  },
  "download_url": "https://s3.amazonaws.com/bucket/zips/processed/PROC-ZIP-001.zip?...",
  "documents_completed": 2,
  "documents_failed": 0
}
```

### PDF Splitting Webhook

**Initial (Job Started):**

```json
{
  "client_job_id": "SPLIT-CONTRACT-2025-001",
  "task_id": "a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6",
  "status": "processing",
  "started_at": "2025-10-03T10:15:30Z",
  "progress": 0,
  "meta_data": { "contract_id": "CNT-2025-001" },
  "documents": [
    {
      "type": "url",
      "document_url": "https://storage.example.com/contract.pdf",
      "status": "queued"
    }
  ],
  "splits": []
}
```

**Progress Update (After Each Split):**

```json
{
  "client_job_id": "SPLIT-CONTRACT-2025-001",
  "task_id": "a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6",
  "status": "processing",
  "started_at": "2025-10-03T10:15:30Z",
  "progress": 33,
  "meta_data": { "contract_id": "CNT-2025-001" },
  "documents": [
    {
      "type": "url",
      "document_url": "https://storage.example.com/contract.pdf",
      "status": "completed",
      "processing_time": 1.5
    }
  ],
  "splits": [
    {
      "output_filename": "cover_page",
      "pages": [1],
      "status": "completed",
      "status_remark": "Completed",
      "download_url": "https://s3.amazonaws.com/...",
      "file_size": 245678,
      "processing_time": 1.2,
      "meta_data": { "section": "cover" }
    }
  ]
}
```

**Final (Job Completed):**

```json
{
  "client_job_id": "SPLIT-CONTRACT-2025-001",
  "task_id": "a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6",
  "status": "completed",
  "started_at": "2025-10-03T10:15:30Z",
  "ended_at": "2025-10-03T10:15:45Z",
  "processing_time": "15.2",
  "progress": 100,
  "meta_data": { "contract_id": "CNT-2025-001" },
  "documents": [
    {
      "type": "url",
      "document_url": "https://storage.example.com/contract.pdf",
      "status": "completed",
      "processing_time": 1.5
    }
  ],
  "splits": [
    {
      "output_filename": "cover_page",
      "pages": [1],
      "status": "completed",
      "status_remark": "Completed",
      "download_url": "https://s3.amazonaws.com/...",
      "file_size": 245678,
      "processing_time": 1.2,
      "meta_data": { "section": "cover" }
    },
    {
      "output_filename": "terms_and_conditions",
      "pages": [2, 3, 4, 5],
      "status": "completed",
      "status_remark": "Completed",
      "download_url": "https://s3.amazonaws.com/...",
      "file_size": 1245678,
      "processing_time": 3.5,
      "meta_data": { "section": "terms" }
    },
    {
      "output_filename": "appendix",
      "pages": [6, 7, 8],
      "status": "completed",
      "status_remark": "Completed",
      "download_url": "https://s3.amazonaws.com/...",
      "file_size": 892341,
      "processing_time": 2.1,
      "meta_data": { "section": "appendix" }
    }
  ]
}
```

---

## Security & Verification

### HMAC Signature

Every webhook is signed with HMAC-SHA256.

**Signature Format:**

```
X-Webhook-Signature: sha256=<hex_digest>
```

**Signature Algorithm:**

```python
import hmac
import hashlib
import json

def generate_signature(payload, secret):
    # 1. Convert payload to JSON string (sorted keys)
    payload_string = json.dumps(payload, sort_keys=True, separators=(',', ':'))

    # 2. Generate HMAC-SHA256
    signature = hmac.new(
        key=secret.encode('utf-8'),
        msg=payload_string.encode('utf-8'),
        digestmod=hashlib.sha256
    ).hexdigest()

    return f"sha256={signature}"
```

### Timestamp Validation

**Prevent Replay Attacks:**

```python
import time

def is_timestamp_valid(timestamp_header, tolerance=300):
    """
    Validate webhook timestamp is within tolerance (default 5 min).

    Args:
        timestamp_header: X-Webhook-Timestamp header value
        tolerance: Max age in seconds

    Returns:
        bool: True if timestamp is valid
    """
    try:
        webhook_time = int(timestamp_header)
        current_time = int(time.time())

        age = current_time - webhook_time
        return 0 <= age <= tolerance
    except (ValueError, TypeError):
        return False
```

---

## Implementation Examples

### Python (Flask)

```python
import hmac
import hashlib
import json
import time
from flask import Flask, request, jsonify

app = Flask(__name__)
WEBHOOK_SECRET = "your_webhook_secret_here"

def verify_webhook_signature(payload, received_signature, secret):
    """Verify HMAC-SHA256 signature."""
    # Generate expected signature
    payload_string = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    expected_signature = hmac.new(
        key=secret.encode('utf-8'),
        msg=payload_string.encode('utf-8'),
        digestmod=hashlib.sha256
    ).hexdigest()

    # Remove 'sha256=' prefix if present
    if received_signature.startswith('sha256='):
        received_signature = received_signature[7:]

    # Constant-time comparison (prevents timing attacks)
    return hmac.compare_digest(expected_signature, received_signature)


@app.route('/webhooks/pdf-toolkit', methods=['POST'])
def handle_webhook():
    # 1. Extract headers
    signature = request.headers.get('X-Webhook-Signature')
    timestamp = request.headers.get('X-Webhook-Timestamp')
    client_job_id = request.headers.get('X-Job-ID')

    if not signature or not timestamp:
        return jsonify({"error": "Missing required headers"}), 400

    # 2. Validate timestamp (prevent replay attacks)
    try:
        webhook_time = int(timestamp)
        current_time = int(time.time())
        if abs(current_time - webhook_time) > 300:  # 5 minutes
            return jsonify({"error": "Webhook timestamp too old"}), 400
    except ValueError:
        return jsonify({"error": "Invalid timestamp"}), 400

    # 3. Get payload
    payload = request.get_json()

    # 4. Verify signature
    if not verify_webhook_signature(payload, signature, WEBHOOK_SECRET):
        return jsonify({"error": "Invalid signature"}), 401

    # 5. Process webhook
    status = payload.get('status')

    if status == 'completed':
        print(f"Job {client_job_id} completed successfully!")
        # Process completed job...

    elif status == 'failed':
        error = payload.get('error')
        print(f"Job {client_job_id} failed: {error}")
        # Handle failure...

    elif status == 'running':
        progress = payload.get('progress', 0)
        print(f"Job {client_job_id} is {progress}% complete")
        # Update progress UI...

    # 6. Return 200 OK (acknowledge receipt)
    return jsonify({"status": "received"}), 200


if __name__ == '__main__':
    app.run(port=8080)
```

### Node.js (Express)

```javascript
const express = require("express");
const crypto = require("crypto");

const app = express();
app.use(express.json());

const WEBHOOK_SECRET = "your_webhook_secret_here";

function verifyWebhookSignature(payload, receivedSignature, secret) {
  // Generate expected signature
  const payloadString = JSON.stringify(payload, Object.keys(payload).sort());
  const expectedSignature = crypto
    .createHmac("sha256", secret)
    .update(payloadString)
    .digest("hex");

  // Remove 'sha256=' prefix if present
  const signature = receivedSignature.startsWith("sha256=")
    ? receivedSignature.substring(7)
    : receivedSignature;

  // Constant-time comparison
  return crypto.timingSafeEqual(
    Buffer.from(expectedSignature),
    Buffer.from(signature)
  );
}

app.post("/webhooks/pdf-toolkit", (req, res) => {
  // 1. Extract headers
  const signature = req.headers["x-webhook-signature"];
  const timestamp = req.headers["x-webhook-timestamp"];
  const jobId = req.headers["x-job-id"];

  if (!signature || !timestamp) {
    return res.status(400).json({ error: "Missing required headers" });
  }

  // 2. Validate timestamp
  const webhookTime = parseInt(timestamp);
  const currentTime = Math.floor(Date.now() / 1000);

  if (Math.abs(currentTime - webhookTime) > 300) {
    // 5 minutes
    return res.status(400).json({ error: "Webhook timestamp too old" });
  }

  // 3. Get payload
  const payload = req.body;

  // 4. Verify signature
  try {
    if (!verifyWebhookSignature(payload, signature, WEBHOOK_SECRET)) {
      return res.status(401).json({ error: "Invalid signature" });
    }
  } catch (error) {
    return res.status(401).json({ error: "Signature verification failed" });
  }

  // 5. Process webhook
  const { status } = payload;

  if (status === "completed") {
    console.log(`Job ${jobId} completed successfully!`);
    // Process completed job...
  } else if (status === "failed") {
    console.log(`Job ${jobId} failed: ${payload.error}`);
    // Handle failure...
  } else if (status === "running") {
    console.log(`Job ${jobId} is ${payload.progress}% complete`);
    // Update progress...
  }

  // 6. Return 200 OK
  res.status(200).json({ status: "received" });
});

app.listen(8080, () => {
  console.log("Webhook server listening on port 8080");
});
```

---

## Best Practices

### Security

✅ **Always verify signatures** - Never trust webhook data without verification
✅ **Validate timestamps** - Prevent replay attacks (5-minute tolerance)
✅ **Use HTTPS** - Never accept webhooks over HTTP
✅ **Rotate secrets regularly** - Every 90 days minimum
✅ **Log failed verifications** - Monitor for potential attacks
✅ **Rate limit webhook endpoint** - Prevent DoS attacks

### Reliability

✅ **Respond quickly** - Return 200 OK within 5 seconds
✅ **Process asynchronously** - Queue webhook for processing
✅ **Handle idempotency** - Same webhook may be sent multiple times
✅ **Monitor failures** - Set up alerts for failed webhooks
✅ **Test with mock data** - Use `/api/v1/webhook/test` endpoint

### Performance

✅ **Minimal validation** - Verify signature, then queue
✅ **Background processing** - Don't block webhook response
✅ **Database connection pooling** - Reuse connections
✅ **Caching** - Cache webhook secrets in memory
✅ **Load balancing** - Distribute webhook traffic

---

## Troubleshooting

### Invalid Signature

**Problem:** `401 Unauthorized - Invalid signature`

**Causes:**

1. Wrong secret used
2. Payload modified before verification
3. JSON serialization mismatch (key order, spacing)

**Solution:**

```python
# Ensure exact JSON serialization match
payload_string = json.dumps(payload, sort_keys=True, separators=(',', ':'))
```

### Timestamp Too Old

**Problem:** `400 Bad Request - Webhook timestamp too old`

**Causes:**

1. Server clock skew
2. Network latency
3. Processing delays

**Solution:**

- Sync server clocks (use NTP)
- Increase tolerance to 10 minutes for testing
- Check firewall/proxy delays

### Webhooks Not Received

**Problem:** No webhooks arriving

**Checklist:**

- [ ] Webhook URL accessible from internet?
- [ ] HTTPS configured correctly?
- [ ] Firewall allows inbound traffic?
- [ ] Webhook URL set in API request?
- [ ] Job actually started (check status endpoint)?

**Debug:**

```bash
# Test webhook endpoint
curl -X POST https://api.houseworks.com/api/v1/webhook/test \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"webhook_url": "https://yourapp.com/webhooks/pdf"}'
```

### Duplicate Webhooks

**Problem:** Same webhook received multiple times

**Cause:** Retry logic (expected behavior)

**Solution:** Implement idempotency

```python
processed_webhooks = set()  # or Redis cache

@app.route('/webhooks/pdf-toolkit', methods=['POST'])
def handle_webhook():
    webhook_id = f"{request.headers.get('X-Job-ID')}_{request.headers.get('X-Webhook-Timestamp')}"

    # Check if already processed
    if webhook_id in processed_webhooks:
        return jsonify({"status": "already_processed"}), 200

    # Process webhook...

    # Mark as processed
    processed_webhooks.add(webhook_id)
    return jsonify({"status": "received"}), 200
```

---

## Testing

### Test Webhook Endpoint

```bash
curl -X POST https://api.houseworks.com/api/v1/webhook/test \
  -H "Authorization: Bearer your_jwt_token" \
  -H "Content-Type: application/json" \
  -d '{
    "webhook_url": "https://yourapp.com/webhooks/pdf-toolkit"
  }'
```

### Mock Webhook for Local Development

```python
import requests
import hmac
import hashlib
import json
import time

def send_mock_webhook(webhook_url, webhook_secret):
    """Send a mock webhook for testing."""

    # Build payload
    payload = {
        "client_job_id": "TEST-123",
        "task_id": "test-task-456",
        "status": "completed",
        "progress": 100,
        "started_at": "2025-10-03T10:00:00Z",
        "ended_at": "2025-10-03T10:00:05Z",
        "processing_time": "5.0",
        "download_url": "https://s3.amazonaws.com/bucket/test.pdf",
        "meta_data": {},
        "documents": [
            {
                "type": "generate",
                "status": "completed",
                "processing_time": 3.2,
                "meta_data": {}
            }
        ],
        "splits": []
    }

    # Generate signature
    payload_string = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    signature = hmac.new(
        webhook_secret.encode('utf-8'),
        payload_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    # Send request
    headers = {
        'Content-Type': 'application/json',
        'X-Webhook-Signature': f'sha256={signature}',
        'X-Webhook-Timestamp': str(int(time.time())),
        'X-Job-ID': 'TEST-123',
        'User-Agent': 'PDF-Toolkit-Webhook/1.0'
    }

    response = requests.post(webhook_url, json=payload, headers=headers)
    print(f"Response: {response.status_code} - {response.text}")

# Test
send_mock_webhook(
    'http://localhost:8080/webhooks/pdf-toolkit',
    'your_webhook_secret'
)
```

---
