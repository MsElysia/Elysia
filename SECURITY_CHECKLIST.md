# Security Checklist - Project Guardian

**Use this checklist before deploying to production**

---

## 🔐 Pre-Deployment Security

### API Key Management
- [ ] All API keys moved to environment variables
- [ ] No API keys in config files or code
- [ ] SecretsManager implemented and tested
- [ ] Old plain text keys removed/deleted
- [ ] API keys rotated (if previously exposed)
- [ ] Master encryption key backed up securely

### Code Security
- [ ] No hardcoded secrets in code
- [ ] `.gitignore` updated to exclude secrets
- [ ] Code review completed
- [ ] Input validation implemented
- [ ] Error messages don't expose sensitive info

### File Permissions
- [ ] Secrets directory: `chmod 700 data/secrets/`
- [ ] Encrypted files: `chmod 600 data/secrets/*.encrypted`
- [ ] Master key: `chmod 600 data/secrets/.master_key`
- [ ] Data directory: `chmod 755 data/`

---

## 🌐 Network Security

### Firewall
- [ ] Only necessary ports open
- [ ] API port (8080) restricted if needed
- [ ] UI port (5000) restricted if exposed
- [ ] Database ports closed (if applicable)

### SSL/TLS
- [ ] SSL certificate obtained
- [ ] HTTPS enabled for API server
- [ ] HTTPS enabled for UI (if exposed)
- [ ] Certificate auto-renewal configured

### Authentication
- [ ] API authentication implemented (if exposed)
- [ ] Rate limiting configured
- [ ] Failed login monitoring enabled
- [ ] Session timeout configured

---

## 🔍 Monitoring & Auditing

### Logging
- [ ] Logging configured and working
- [ ] Logs exclude sensitive data
- [ ] Log rotation enabled
- [ ] Log retention policy set

### Monitoring
- [ ] Health checks configured
- [ ] Metrics collection enabled
- [ ] Alerting set up (if needed)
- [ ] Uptime monitoring configured

### Audit Trail
- [ ] Security events logged
- [ ] Mutation history tracked
- [ ] Trust changes recorded
- [ ] Authentication attempts logged

---

## 📦 Dependencies

### Package Security
- [ ] All dependencies up to date
- [ ] Security vulnerabilities checked
- [ ] Unused dependencies removed
- [ ] Requirements file locked to versions

### Updates
- [ ] Regular update schedule planned
- [ ] Security patch process defined
- [ ] Dependency audit tool configured

---

## 🛡️ System Hardening

### Configuration
- [ ] Default passwords changed
- [ ] Debug mode disabled in production
- [ ] Verbose logging disabled
- [ ] Error messages generic (no stack traces)

### Access Control
- [ ] Master-slave authentication verified
- [ ] Trust scores configured appropriately
- [ ] Access controls tested
- [ ] Privilege escalation prevented

### Data Protection
- [ ] Backups encrypted
- [ ] Data at rest encrypted (if needed)
- [ ] Data in transit encrypted (HTTPS/TLS)
- [ ] GDPR/compliance checked (if applicable)

---

## ✅ Production Readiness

### Testing
- [ ] System tested in staging
- [ ] Security tests completed
- [ ] Load testing performed
- [ ] Failover tested

### Documentation
- [ ] Deployment guide reviewed
- [ ] Security procedures documented
- [ ] Incident response plan ready
- [ ] Rollback procedure documented

### Operations
- [ ] Backup strategy defined
- [ ] Recovery procedure tested
- [ ] Monitoring dashboards set up
- [ ] On-call procedures defined

---

## 🔄 Ongoing Security

### Regular Tasks
- [ ] Weekly: Review logs for anomalies
- [ ] Monthly: Security updates applied
- [ ] Quarterly: Security audit performed
- [ ] Annually: Penetration testing (if needed)

### Key Rotation
- [ ] API keys rotated quarterly
- [ ] Master encryption key rotation plan
- [ ] Token expiration configured
- [ ] Certificate renewal automated

---

## 📋 Quick Security Check

Run these commands before deployment:

```bash
# Check for exposed secrets
grep -r "sk-" project_guardian/ --exclude-dir=__pycache__
grep -r "api_key" config/  # Should be empty or templates only

# Verify file permissions
ls -la data/secrets/

# Check environment variables
env | grep -i api_key  # Should show variables, not values in logs

# Test SecretsManager
python -c "from project_guardian.secrets_manager import get_api_key; print('OK' if get_api_key('openai') else 'FAIL')"
```

---

**Status**: Complete security checklist ready for use!




















