# Migration Guide - Securing API Keys

**Purpose**: Migrate from plain text API keys to secure storage

---

## 🔐 Why Migrate?

**Current State**: API keys stored in plain text config files  
**Security Risk**: Keys exposed if files are committed or shared  
**Solution**: Use environment variables + encrypted storage

---

## 📋 Migration Steps

### Step 1: Install Dependencies

```bash
pip install cryptography
```

### Step 2: Run Migration Script

```python
from project_guardian.secrets_manager import SecretsManager

# Create secrets manager
manager = SecretsManager()

# Migrate from config file
migrated_count = manager.migrate_from_config("config/guardian_config.json")

print(f"Migrated {migrated_count} API keys to secure storage")
```

### Step 3: Set Environment Variables (Recommended)

```bash
# Windows
set OPENAI_API_KEY=your-actual-key-here
set CLAUDE_API_KEY=your-actual-key-here

# Linux/Mac
export OPENAI_API_KEY=your-actual-key-here
export CLAUDE_API_KEY=your-actual-key-here
```

### Step 4: Update Code to Use SecretsManager

**Before**:
```python
# ❌ Old way - from config file
config = load_config()
api_key = config["api_keys"]["openai_api_key"]
```

**After**:
```python
# ✅ New way - secure
from project_guardian.secrets_manager import get_api_key

api_key = get_api_key("openai")
# Automatically checks env vars first, then encrypted storage
```

### Step 5: Rotate Exposed Keys

If keys were in plain text files that may have been shared:

1. **Generate new API keys** from provider dashboards
2. **Update environment variables** with new keys
3. **Revoke old keys** in provider settings
4. **Test system** with new keys

---

## 🔒 Secure Storage Locations

After migration:

- **Encrypted Secrets**: `data/secrets/*.encrypted`
- **Master Key**: `data/secrets/.master_key` (keep this secret!)
- **Environment Variables**: System environment (preferred)

---

## 📝 .gitignore Updates

Add these to `.gitignore`:

```
# Secrets
data/secrets/
*.encrypted
.master_key

# API Keys
config/*api*key*.json
**/api*key*.txt
```

---

## ✅ Verification

Check migration success:

```python
from project_guardian.secrets_manager import get_secrets_manager

manager = get_secrets_manager()

# List all secrets (without values)
secrets = manager.get_all_secrets()
print(f"Found {len(secrets)} secrets")

# Test retrieval
api_key = manager.get_secret("openai_api_key")
if api_key:
    print("✅ Migration successful!")
else:
    print("⚠️  No key found - check configuration")
```

---

## 🚨 Important Notes

1. **Backup First**: Backup existing config files before migration
2. **Test System**: Verify system works after migration
3. **Delete Old Files**: Remove API keys from plain text configs (after verifying)
4. **Keep Master Key Safe**: The `.master_key` file is required to decrypt secrets
5. **Environment Preferred**: Always use environment variables for production

---

## 🔄 Rollback (If Needed)

If migration causes issues:

```python
# Restore from backup
# Or manually restore config files
# Then revert code changes
```

---

**Status**: Ready for migration. Run migration script when ready.




















