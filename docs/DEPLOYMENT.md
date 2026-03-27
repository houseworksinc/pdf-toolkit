# Deployment Guide

Production deployment guide for HouseWorks PDF Toolkit.

---

## Deployment Options

1. [Docker Compose (Recommended)](#docker-compose-deployment)
2. [GitHub Actions CI/CD](#github-actions-deployment)
3. [Kubernetes](#kubernetes-deployment)
4. [AWS ECS/Fargate](#aws-deployment)
5. [Systemd Services](#systemd-deployment)

---

## Docker Compose Deployment

### Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- 2GB RAM minimum
- 10GB disk space

### Step 1: Configuration

```bash
# Clone repository
git clone <repository-url>
cd pdf-toolkit

# Create .env file
cp .env.example .env
```

**Production .env:**

```bash
# JWT
JWT_SECRET_KEY=$(openssl rand -base64 32)
JWT_ACCESS_TOKEN_EXPIRES=86400

# Admin
MASTER_USERNAME=admin
MASTER_PASSWORD=$(openssl rand -base64 16)

# Celery
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# AWS
AWS_S3_BUCKET_NAME=prod-pdf-bucket
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=<from-aws-iam>
AWS_SECRET_ACCESS_KEY=<from-aws-iam>

# Application
ENV=production
LOG_LEVEL=INFO

# Template Cache (optional)
TEMPLATE_CACHE_ENABLED=true
TEMPLATE_CACHE_DIR=/app/template_cache
TEMPLATE_CACHE_MAX_SIZE_MB=500
TEMPLATE_CACHE_TTL_DAYS=7
```

### Step 2: Deploy

```bash
# Build and start services
docker-compose up -d --build

# Check status
docker-compose ps

# View logs
docker-compose logs -f

# Scale workers
docker-compose up -d --scale worker=3
```

### Step 3: Health Check

```bash
curl http://localhost:5001/
```

Expected response:

```json
{
  "message": "Hello world"
}
```

### Step 4: Create First User

```bash
TOKEN=$(curl -X POST http://localhost:5001/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"secure_password"}' \
  | jq -r '.webhook_secret')

echo "Webhook Secret: $TOKEN"
```

---

## Kubernetes Deployment

### Manifests

**Namespace:**

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: pdf-toolkit
```

**ConfigMap:**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: pdf-config
  namespace: pdf-toolkit
data:
  CELERY_BROKER_URL: "redis://redis-service:6379/0"
  AWS_REGION: "us-east-1"
  LOG_LEVEL: "INFO"
```

**Secrets:**

```bash
kubectl create secret generic pdf-secrets \
  --from-literal=JWT_SECRET_KEY=<your-secret> \
  --from-literal=AWS_ACCESS_KEY_ID=<key> \
  --from-literal=AWS_SECRET_ACCESS_KEY=<secret> \
  -n pdf-toolkit
```

**API Deployment:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pdf-api
  namespace: pdf-toolkit
spec:
  replicas: 3
  selector:
    matchLabels:
      app: pdf-api
  template:
    metadata:
      labels:
        app: pdf-api
    spec:
      containers:
        - name: api
          image: pdf-toolkit:latest
          ports:
            - containerPort: 8000
          envFrom:
            - configMapRef:
                name: pdf-config
            - secretRef:
                name: pdf-secrets
          resources:
            requests:
              cpu: 500m
              memory: 512Mi
            limits:
              cpu: 1000m
              memory: 1Gi
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 30
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 5
```

**Worker Deployment:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pdf-worker
  namespace: pdf-toolkit
spec:
  replicas: 5
  selector:
    matchLabels:
      app: pdf-worker
  template:
    metadata:
      labels:
        app: pdf-worker
    spec:
      containers:
        - name: worker
          image: pdf-toolkit:latest
          command:
            [
              "celery",
              "-A",
              "app.workers.celery_worker:celery",
              "worker",
              "--loglevel=info",
            ]
          envFrom:
            - configMapRef:
                name: pdf-config
            - secretRef:
                name: pdf-secrets
          resources:
            requests:
              cpu: 1000m
              memory: 2Gi
            limits:
              cpu: 2000m
              memory: 4Gi
```

**Service:**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: pdf-api-service
  namespace: pdf-toolkit
spec:
  selector:
    app: pdf-api
  ports:
    - protocol: TCP
      port: 80
      targetPort: 8000
  type: LoadBalancer
```

### Deploy

```bash
kubectl apply -f k8s/
kubectl get pods -n pdf-toolkit
kubectl logs -f deployment/pdf-api -n pdf-toolkit
```

---

## AWS Deployment

### ECS Task Definition

```json
{
  "family": "pdf-toolkit",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "containerDefinitions": [
    {
      "name": "pdf-api",
      "image": "<account-id>.dkr.ecr.us-east-1.amazonaws.com/pdf-toolkit:latest",
      "portMappings": [{ "containerPort": 8000 }],
      "environment": [
        {
          "name": "CELERY_BROKER_URL",
          "value": "redis://redis.cache.amazonaws.com:6379/0"
        },
        { "name": "AWS_REGION", "value": "us-east-1" }
      ],
      "secrets": [
        { "name": "JWT_SECRET_KEY", "valueFrom": "arn:aws:secretsmanager:..." }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/pdf-toolkit",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "api"
        }
      }
    }
  ]
}
```

### ECS Service

```bash
aws ecs create-service \
  --cluster pdf-toolkit-cluster \
  --service-name pdf-api-service \
  --task-definition pdf-toolkit:1 \
  --desired-count 3 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}"
```

---

## Systemd Deployment

**API Service:**

```ini
[Unit]
Description=PDF Toolkit API
After=network.target

[Service]
Type=simple
User=pdfgen
WorkingDirectory=/opt/pdf-toolkit
Environment="PATH=/opt/pdf-toolkit/venv/bin"
EnvironmentFile=/opt/pdf-toolkit/.env
ExecStart=/opt/pdf-toolkit/venv/bin/gunicorn -w 4 -b 0.0.0.0:8000 app.main:app
Restart=always

[Install]
WantedBy=multi-user.target
```

**Worker Service:**

```ini
[Unit]
Description=PDF Toolkit Worker
After=network.target redis.service

[Service]
Type=simple
User=pdfgen
WorkingDirectory=/opt/pdf-toolkit
Environment="PATH=/opt/pdf-toolkit/venv/bin"
EnvironmentFile=/opt/pdf-toolkit/.env
ExecStart=/opt/pdf-toolkit/venv/bin/celery -A app.workers.celery_worker:celery worker --loglevel=info
Restart=always

[Install]
WantedBy=multi-user.target
```

**Enable and Start:**

```bash
sudo systemctl enable pdf-api pdf-worker
sudo systemctl start pdf-api pdf-worker
sudo systemctl status pdf-api pdf-worker
```

---

## Production Checklist

### Security

- [ ] Change default admin password
- [ ] Generate strong JWT secret (32+ chars)
- [ ] Enable HTTPS (use Let's Encrypt or AWS ALB)
- [ ] Configure firewall (only ports 80, 443 open)
- [ ] Use AWS IAM roles (not access keys)
- [ ] Enable audit logging
- [ ] Set up rate limiting (nginx)
- [ ] Rotate webhook secrets regularly

### Performance

- [ ] Scale workers based on load (min: 3)
- [ ] Enable Redis persistence (AOF + RDB)
- [ ] Configure S3 lifecycle policies
- [ ] Set up CDN for static assets
- [ ] Enable database backups (daily)
- [ ] Monitor queue depth
- [ ] Set resource limits (CPU, memory)

### Monitoring

- [ ] Set up health check endpoints
- [ ] Configure log aggregation (CloudWatch, Datadog)
- [ ] Set up alerts (high error rate, queue depth)
- [ ] Monitor API latency (p95, p99)
- [ ] Track S3 upload success rate
- [ ] Monitor Celery worker health

### Backup & Recovery

- [ ] Automated database backups
- [ ] S3 versioning enabled
- [ ] Test restore procedures
- [ ] Document recovery steps
- [ ] Set up disaster recovery runbook

---

## Troubleshooting

### API Not Responding

```bash
# Check logs
docker-compose logs api

# Check process
ps aux | grep gunicorn

# Check port
netstat -tulpn | grep 5001
```

### Workers Not Processing

```bash
# Check Celery
docker-compose logs worker

# Check Redis
redis-cli ping

# Inspect queue
redis-cli llen celery
```

### High Memory Usage

```bash
# Monitor
docker stats

# Restart workers
docker-compose restart worker
```

---
