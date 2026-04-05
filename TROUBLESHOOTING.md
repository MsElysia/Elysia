# Troubleshooting Guide - Project Guardian

**Last Updated**: November 2, 2025

---

## 🚨 Common Issues

### System Won't Start

#### Issue: System hangs during initialization

**Symptoms**:
- System starts but never completes initialization
- Hangs at "Initializing operational components..."

**Solutions**:
1. **Check logs**: `logs/guardian.log`
2. **Verify file permissions**: Ensure data directory is writable
3. **Check for blocking I/O**: Should be fixed in latest version
4. **Run with debug**: `python -m project_guardian --log-level DEBUG`

**Prevention**: Use lazy loading (already implemented)

---

#### Issue: Import errors

**Symptoms**:
```
ModuleNotFoundError: No module named 'X'
```

**Solutions**:
1. Install missing package: `pip install X`
2. Check virtual environment activated
3. Verify Python version: `python --version` (need 3.10+)
4. Reinstall dependencies: `pip install -r requirements.txt`

---

#### Issue: Configuration errors

**Symptoms**:
```
KeyError: 'api_key'
ConfigurationError: Invalid config
```

**Solutions**:
1. Run setup wizard: `python setup_guardian.py`
2. Check config file: `config/guardian_config.json`
3. Verify environment variables set
4. Use SecretsManager: `from project_guardian.secrets_manager import get_api_key`

---

### API Keys Not Working

#### Issue: AI features return errors

**Symptoms**:
- "API key required" errors
- 401 Unauthorized responses
- AI providers not working

**Solutions**:
1. **Check environment variables**:
   ```bash
   # Windows
   echo %OPENAI_API_KEY%
   
   # Linux/Mac
   echo $OPENAI_API_KEY
   ```

2. **Verify key format**: Keys should start with `sk-` (OpenAI) or `sk-ant-` (Claude)

3. **Test key directly**:
   ```python
   import os
   key = os.getenv("OPENAI_API_KEY")
   print(f"Key found: {key[:10]}..." if key else "No key found")
   ```

4. **Use SecretsManager**:
   ```python
   from project_guardian.secrets_manager import get_api_key
   key = get_api_key("openai")
   ```

5. **Check encrypted storage**: `data/secrets/openai_api_key.encrypted`

---

#### Issue: Key rotation needed

**Symptoms**:
- Keys exposed in plain text files
- Security audit flagged keys

**Solutions**:
1. Generate new keys from provider dashboard
2. Update environment variables
3. Run migration: `python -m project_guardian.secrets_manager`
4. Revoke old keys
5. Test with new keys

---

### Memory Issues

#### Issue: System running out of memory

**Symptoms**:
- Slow performance
- OutOfMemory errors
- High memory usage

**Solutions**:
1. **Reduce memory history**:
   ```python
   memory.max_items = 5000  # Reduce from default
   ```

2. **Clean old memories**:
   ```python
   memory.cleanup(days=30)  # Remove memories older than 30 days
   ```

3. **Disable vector search** (if not needed):
   ```python
   memory = MemoryCore(enable_vector_search=False)
   ```

4. **Increase system memory**: Add RAM or swap space

---

#### Issue: Memory corruption

**Symptoms**:
- Corrupted data errors
- JSON decode errors
- Memory file unreadable

**Solutions**:
1. **Restore from backup**: `data/backups/guardian_memory.json.YYYYMMDD`
2. **RecoveryVault**: Use system snapshots
3. **Rebuild memory**: Start fresh (loses data)
4. **Check disk space**: Ensure enough space for files

---

### Mutation System Issues

#### Issue: Mutations rejected

**Symptoms**:
- Mutations always rejected
- Trust score too low

**Solutions**:
1. **Check trust score**:
   ```python
   from project_guardian.trust_registry import TrustRegistry
   registry = TrustRegistry()
   score = registry.get_node("your_node_id")
   print(score.trust_scores)
   ```

2. **Increase trust**:
   - Complete successful tasks
   - Register with higher initial trust
   - Build trust over time

3. **Review mutation**:
   - Check risk level
   - Verify syntax valid
   - Ensure safe changes

---

#### Issue: Mutation rollback failed

**Symptoms**:
- Rollback doesn't restore code
- Snapshot missing

**Solutions**:
1. **Check RecoveryVault**:
   ```python
   from project_guardian.recovery_vault import RecoveryVault
   vault = RecoveryVault()
   snapshots = vault.list_snapshots()
   ```

2. **Manual restore**:
   - Use Git if available
   - Restore from backup
   - Revert manually

3. **Prevention**: Always create snapshot before mutation

---

### Network Issues

#### Issue: API calls timing out

**Symptoms**:
- Network errors
- Timeout exceptions
- Connection refused

**Solutions**:
1. **Check internet connection**
2. **Verify API endpoints**: Provider status pages
3. **Check rate limits**: Too many requests
4. **Retry logic**: System has automatic retries
5. **Use fallback providers**: System tries multiple providers

---

#### Issue: Slave connection fails

**Symptoms**:
- Cannot connect to slaves
- Authentication failures

**Solutions**:
1. **Verify network connectivity**: Can reach slave host
2. **Check authentication tokens**: Tokens must match
3. **Review firewall rules**: Ports must be open
4. **Check slave status**: Slave must be running
5. **Regenerate tokens**: If compromised

---

### Performance Issues

#### Issue: System slow

**Symptoms**:
- Slow response times
- High CPU usage
- Lag in operations

**Solutions**:
1. **Monitor resources**: `htop` or Task Manager
2. **Check for blocking operations**: Should be async
3. **Reduce concurrent tasks**: Limit task queue
4. **Optimize memory usage**: Clean old data
5. **Upgrade hardware**: More RAM/CPU

---

#### Issue: High API costs

**Symptoms**:
- Excessive API calls
- High provider bills

**Solutions**:
1. **Enable caching**: Cache AI responses
2. **Batch requests**: Combine multiple requests
3. **Use cheaper models**: When appropriate
4. **Rate limiting**: Limit requests per minute
5. **Monitor usage**: Track API call counts

---

### Testing Issues

#### Issue: Pytest hangs

**Symptoms**:
- Tests never complete
- Hangs during collection

**Solutions**:
1. **Use manual verification**: `python verify_system.py`
2. **Test modules individually**: Not full suite
3. **Check for blocking imports**: Remove problematic imports
4. **Use API tests**: Test via HTTP instead

---

## 🔍 Diagnostic Tools

### System Status

```python
from project_guardian.system_orchestrator import SystemOrchestrator

orchestrator = SystemOrchestrator()
status = orchestrator.get_system_status()
print(status)
```

### Health Check

```bash
curl http://localhost:8080/api/health
```

### Log Analysis

```bash
# Find errors
grep ERROR logs/guardian.log

# Count errors
grep -c ERROR logs/guardian.log

# Last 100 lines
tail -100 logs/guardian.log
```

### Memory Check

```python
from project_guardian.memory import MemoryCore

memory = MemoryCore()
stats = memory.get_statistics()
print(f"Total memories: {stats['total']}")
print(f"Categories: {stats['categories']}")
```

---

## 📞 Getting Help

### Self-Service

1. Check logs: `logs/guardian.log`
2. Review documentation: `USER_GUIDE.md`
3. Run diagnostics: `python verify_system.py`
4. Check status: Health endpoint

### Collecting Information

When reporting issues, include:
- Error messages from logs
- System configuration
- Python version
- Operating system
- Steps to reproduce

---

## ✅ Prevention

### Best Practices

1. **Regular Backups**: Automatic backups enabled
2. **Monitor Health**: Check health endpoint regularly
3. **Update Dependencies**: Keep packages current
4. **Secure Secrets**: Use environment variables
5. **Test Changes**: Test in development first

---

**Status**: Comprehensive troubleshooting guide complete!




















