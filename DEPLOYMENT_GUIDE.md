# Deployment Guide - Project Guardian

**Version**: 1.0  
**Last Updated**: November 2, 2025

---

## 📋 Table of Contents

1. [Pre-Deployment Checklist](#pre-deployment-checklist)
2. [Deployment Methods](#deployment-methods)
3. [Production Configuration](#production-configuration)
4. [Security Setup](#security-setup)
5. [Monitoring & Maintenance](#monitoring--maintenance)
6. [Scaling & Performance](#scaling--performance)

---

## ✅ Pre-Deployment Checklist

### System Requirements

- [ ] Python 3.10+ installed
- [ ] 2GB+ RAM available
- [ ] 500MB+ disk space
- [ ] Network access (if using external APIs)
- [ ] SSL certificate (for HTTPS in production)

### Dependencies

- [ ] All Python packages installed
- [ ] Cryptography library for secrets
- [ ] Optional: psutil for monitoring
- [ ] Optional: sentence-transformers for vector search

### Security

- [ ] API keys secured (environment variables or encrypted)
- [ ] Secrets directory permissions set correctly
- [ ] Firewall configured (if applicable)
- [ ] SSL/TLS enabled (for web UI/API)
- [ ] Master key backed up securely

---

## 🚀 Deployment Methods

### Method 1: Local Deployment (Development)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure
python setup_guardian.py

# 3. Set environment variables
export OPENAI_API_KEY=sk-...
export CLAUDE_API_KEY=sk-ant-...

# 4. Run
python -m project_guardian
```

### Method 2: Systemd Service (Linux Production)

Create `/etc/systemd/system/guardian.service`:

```ini
[Unit]
Description=Project Guardian AI System
After=network.target

[Service]
Type=simple
User=guardian
WorkingDirectory=/opt/guardian
Environment="OPENAI_API_KEY=sk-..."
Environment="CLAUDE_API_KEY=sk-ant-..."
Environment="PYTHONUNBUFFERED=1"
ExecStart=/usr/bin/python3 -m project_guardian
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable guardian
sudo systemctl start guardian
sudo systemctl status guardian
```

### Method 3: Docker Deployment

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY project_guardian/ ./project_guardian/
COPY config/ ./config/

# Create data directory
RUN mkdir -p data logs

# Set environment
ENV PYTHONUNBUFFERED=1

# Run
CMD ["python", "-m", "project_guardian"]
```

Build and run:
```bash
docker build -t guardian .
docker run -d \
  --name guardian \
  -e OPENAI_API_KEY=sk-... \
  -e CLAUDE_API_KEY=sk-ant-... \
  -v $(pwd)/data:/app/data \
  -p 8080:8080 \
  guardian
```

### Method 4: Windows Service

Use NSSM (Non-Sucking Service Manager):

```bash
# Install NSSM
nssm install Guardian "C:\Python\python.exe" "-m project_guardian"

# Set environment variables
nssm set Guardian AppEnvironmentExtra "OPENAI_API_KEY=sk-..."
nssm set Guardian AppEnvironmentExtra "CLAUDE_API_KEY=sk-ant-..."

# Start service
nssm start Guardian
```

---

## ⚙️ Production Configuration

### Recommended Settings

```json
{
  "log_level": "INFO",
  "enable_debug": false,
  "heartbeat_interval": 30,
  "max_memory_items": 10000,
  "api_server": {
    "host": "0.0.0.0",
    "port": 8080,
    "enable_cors": true,
    "ssl_enabled": true
  },
  "security": {
    "require_authentication": true,
    "session_timeout": 3600,
    "max_failed_attempts": 5
  }
}
```

### Environment Variables

```bash
# Required
OPENAI_API_KEY=sk-...
CLAUDE_API_KEY=sk-ant-...

# Optional but Recommended
GUARDIAN_LOG_LEVEL=INFO
GUARDIAN_DATA_DIR=/var/lib/guardian
GUARDIAN_SECRETS_DIR=/var/lib/guardian/secrets
GUARDIAN_API_PORT=8080
GUARDIAN_ENABLE_SSL=true
```

---

## 🔒 Security Setup

### 1. API Keys

**Never** store in:
- ❌ Code files
- ❌ Config files in version control
- ❌ Environment files in repo

**Always** use:
- ✅ Environment variables (production)
- ✅ Encrypted secrets storage (fallback)
- ✅ Secure key management system

### 2. Network Security

```bash
# Firewall rules (UFW example)
ufw allow 8080/tcp  # API server
ufw allow 5000/tcp  # UI (if exposed)

# Or restrict to specific IPs
ufw allow from 192.168.1.0/24 to any port 8080
```

### 3. SSL/TLS

```bash
# Using Let's Encrypt (certbot)
sudo certbot --nginx -d yourdomain.com

# Or self-signed for testing
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout key.pem -out cert.pem -days 365
```

### 4. File Permissions

```bash
# Secrets directory
chmod 700 data/secrets/
chmod 600 data/secrets/*.encrypted
chmod 600 data/secrets/.master_key

# Data directory
chmod 755 data/
```

---

## 📊 Monitoring & Maintenance

### Health Checks

```bash
# Health endpoint
curl http://localhost:8080/api/health

# Metrics endpoint
curl http://localhost:8080/api/metrics
```

### Log Monitoring

```bash
# Watch logs
tail -f logs/guardian.log

# Check errors
grep ERROR logs/guardian.log

# Rotate logs (logrotate)
/etc/logrotate.d/guardian:
/var/log/guardian/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
}
```

### Backup Strategy

```bash
# Backup data directory
tar -czf guardian-backup-$(date +%Y%m%d).tar.gz data/

# Backup secrets (encrypted)
cp -r data/secrets/ backups/secrets-$(date +%Y%m%d)/

# Automated backup script
0 2 * * * /usr/local/bin/backup-guardian.sh
```

---

## 📈 Scaling & Performance

### Resource Limits

```bash
# Systemd resource limits
[Service]
MemoryMax=2G
CPUQuota=100%
```

### Performance Tuning

1. **Memory Management**
   - Set `max_memory_items` based on available RAM
   - Enable memory cleanup
   - Use vector search only if needed

2. **Database Optimization**
   - SQLite: Regular VACUUM
   - Consider PostgreSQL for large deployments

3. **API Rate Limiting**
   - Implement rate limiting
   - Cache responses when possible
   - Batch API calls

### Load Balancing

If running multiple instances:

```nginx
upstream guardian {
    server localhost:8080;
    server localhost:8081;
    server localhost:8082;
}

server {
    listen 80;
    location / {
        proxy_pass http://guardian;
    }
}
```

---

## 🔧 Troubleshooting

### System Won't Start

1. Check logs: `logs/guardian.log`
2. Verify dependencies: `pip list`
3. Test configuration: `python -c "from project_guardian.config_validator import ConfigValidator; ..."`
4. Check ports: `netstat -an | grep 8080`

### Performance Issues

1. Monitor resources: `htop` or Task Manager
2. Check memory usage
3. Review API call frequency
4. Check database size

### Security Issues

1. Verify API keys not exposed
2. Check file permissions
3. Review authentication logs
4. Monitor for failed login attempts

---

## 🎯 Post-Deployment

### Verification Steps

1. ✅ System starts successfully
2. ✅ Health endpoint responds
3. ✅ API endpoints accessible
4. ✅ Logs show no errors
5. ✅ Memory/CPU usage normal

### Ongoing Maintenance

- [ ] Daily: Check health endpoint
- [ ] Weekly: Review logs
- [ ] Monthly: Backup data
- [ ] Quarterly: Security audit
- [ ] As needed: Update dependencies

---

## 📞 Support

See `USER_GUIDE.md` for:
- Feature usage
- API documentation
- Troubleshooting guide

---

**Status**: Production-ready deployment guide complete!




















