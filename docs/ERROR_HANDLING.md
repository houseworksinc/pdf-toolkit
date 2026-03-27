# Error Handling Documentation

## Overview

This document describes the error handling mechanisms implemented in the PDF Toolkit microservice to provide user-friendly error messages for database and API operations.

## Global Error Handlers

The service now includes global error handlers that automatically catch and format PostgreSQL/SQLAlchemy exceptions into readable error messages.

### Handled Exception Types

1. **IntegrityError** - Constraint violations (unique, foreign key, not null)
2. **DataError** - Invalid data (wrong type, too long, invalid format)
3. **OperationalError** - Database connection issues
4. **DatabaseError** - Generic database errors
5. **HTTPException** - HTTP protocol errors

## Error Response Format

All errors now return a consistent JSON format:

```json
{
  "error": "User-friendly error message",
  "status_code": 400
}
```

## Common Error Scenarios

### 1. Duplicate client_job_id

**Scenario:** Client sends a request with a `client_job_id` that already exists in the database.

**Old Response:**

```
500 Internal Server Error
sqlalchemy.exc.IntegrityError: (psycopg2.errors.UniqueViolation) duplicate key value violates unique constraint "pdf_jobs_job_id_key"
DETAIL:  Key (client_job_id)=(abc123) already exists.
```

**New Response:**

```json
{
  "error": "A job with this client_job_id already exists",
  "status_code": 409
}
```

### 2. Missing client_job_id

**Scenario:** Client sends a request without `client_job_id` (or empty string).

**Response:**

```json
{
  "error": "Missing required parameters",
  "status_code": 400
}
```

If somehow the validation is bypassed and reaches the database:

```json
{
  "error": "client_job_id is required and cannot be empty",
  "status_code": 400
}
```

### 3. Field too long

**Scenario:** Client sends a `client_job_id` longer than 255 characters.

**Old Response:**

```
500 Internal Server Error
sqlalchemy.exc.DataError: (psycopg2.errors.CheckViolation) new row for relation "pdf_jobs" violates check constraint "check_job_id_length"
```

**New Response:**

```json
{
  "error": "One or more fields exceed the maximum allowed length",
  "status_code": 400
}
```

### 4. Invalid data format

**Scenario:** Client sends data in an invalid format.

**Old Response:**

```
500 Internal Server Error
sqlalchemy.exc.DataError: (psycopg2.errors.InvalidTextRepresentation) invalid input syntax for type json
```

**New Response:**

```json
{
  "error": "Invalid data format provided",
  "status_code": 400
}
```

### 5. Database connection error

**Scenario:** Database is unavailable or connection fails.

**Old Response:**

```
500 Internal Server Error
sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) could not connect to server: Connection refused
```

**New Response:**

```json
{
  "error": "Database connection error. Please try again later",
  "status_code": 503
}
```

### 6. Foreign key violation

**Scenario:** Client references a client_job_id that doesn't exist (for split operations).

**Old Response:**

```
500 Internal Server Error
sqlalchemy.exc.IntegrityError: (psycopg2.errors.ForeignKeyViolation) insert or update on table "pdf_split_outputs" violates foreign key constraint
```

**New Response:**

```json
{
  "error": "Referenced record does not exist",
  "status_code": 400
}
```

## Implementation Details

### Error Handler Module (`app/error_handlers.py`)

- Centralized error formatting logic
- Registered globally in Flask app initialization
- Automatic rollback of failed database transactions
- Comprehensive logging of all errors

### Database Operations (`app/database.py`)

Key functions now include try-catch blocks:

- `log_request()` - Handles job creation errors
- `log_split_outputs()` - Handles split output creation errors
- `create_user()` - Handles user creation errors

Each function:

1. Attempts the database operation
2. Catches specific exceptions (IntegrityError, DatabaseError)
3. Rolls back the transaction
4. Logs the error with context
5. Re-raises the exception for the global handler to format

### Logging

All database errors are logged with context:

- Operation being performed
- Relevant identifiers (client_job_id, username, etc.)
- Full exception details

Logs are written to:

- Console output
- `logs/app.log` (rotating file handler, 10MB max, 10 backups)

## Testing

To test the error handling:

### Test duplicate client_job_id:

```bash
# First request - should succeed
curl -X POST http://localhost:5000/api/v1/generate-pdf \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "client_job_id": "test123",
    "template_url": "https://example.com/template.docx",
    "data": {"name": "Test"}
  }'

# Second request with same client_job_id - should return 409
curl -X POST http://localhost:5000/api/v1/generate-pdf \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "client_job_id": "test123",
    "template_url": "https://example.com/template.docx",
    "data": {"name": "Test"}
  }'
```

Expected response:

```json
{
  "error": "A job with this client_job_id already exists",
  "status_code": 409
}
```

### Test field too long:

```bash
curl -X POST http://localhost:5000/api/v1/generate-pdf \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "client_job_id": "'$(python3 -c "print('a' * 300)")'",
    "template_url": "https://example.com/template.docx",
    "data": {"name": "Test"}
  }'
```

Expected response:

```json
{
  "error": "One or more fields exceed the maximum allowed length",
  "status_code": 400
}
```

## Benefits

1. **Better Developer Experience**: Clear, actionable error messages
2. **Easier Debugging**: Specific errors help identify issues quickly
3. **Consistent API**: All errors follow the same format
4. **Security**: Internal database details are not exposed
5. **Logging**: All errors are logged for monitoring and debugging
6. **Automatic Rollback**: Failed transactions are rolled back automatically

## Affected Endpoints

All endpoints that interact with the database now benefit from error handling:

- `/api/v1/generate-pdf` (POST)
- `/api/v1/generate-pdf/dynamic` (POST)
- `/api/v1/generate-pdf/status` (GET)
- `/api/v1/split-pdf` (POST)
- `/api/v1/split-pdf/status` (GET)
- `/api/v1/merge-pdfs` (POST)
- `/api/v1/merge-pdfs/status` (GET)
- `/api/v1/zip-files` (POST)
- Auth endpoints
- User management endpoints
