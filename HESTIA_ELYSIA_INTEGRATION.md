# Hestia-Elysia Integration Guide

## Overview
This document describes the integration between Elysia AI system and Hestia Real Estate Platform, including F: drive memory storage configuration.

---

## ✅ What's Been Integrated

### 1. **Hestia Bridge** (`hestia_bridge.py`)
- Connects Elysia with Hestia Real Estate Platform
- Checks if Hestia is running (port 8501)
- Can start Hestia automatically if needed
- Reads property data from Hestia outputs
- Syncs real estate data with Elysia memory
- Provides investment insights and recommendations

### 2. **Memory Storage Configuration** (`memory_storage_config.py`)
- **Primary Storage**: F: drive (thumb drive) at `F:/ElysiaMemory`
- **Fallback**: Local storage at `~/ElysiaMemory` if F: unavailable
- Automatic path detection and write testing
- Backup system for memory files
- Configures all memory, trust, and task files

### 3. **Unified Runner** (`run_elysia_unified.py`)
- Updated to use F: drive for memory
- Integrated Hestia bridge
- Shows Hestia connection status
- Automatic storage path configuration

---

## 🚀 Usage

### Starting Unified System

```bash
# Run the unified Elysia system
python run_elysia_unified.py

# Or use the batch file
START_ELYSIA_UNIFIED.bat
```

The system will:
1. ✅ Check for F: drive and configure memory storage
2. ✅ Initialize all Elysia modules
3. ✅ Connect to Hestia (if running)
4. ✅ Show status of all components

### Memory Storage

**Primary Location**: `F:/ElysiaMemory/`
- `guardian_memory.json` - Main memory file
- `enhanced_trust.json` - Trust matrix
- `enhanced_tasks.json` - Task engine
- `backups/` - Automatic backups

**Fallback**: `~/ElysiaMemory/` (if F: unavailable)

### Hestia Integration

**Hestia Path**: `C:\Users\mrnat\Hestia`
**Hestia Port**: `8501` (Streamlit)

**Features**:
- Reads property data from `Hestia/outputs/scored_listings.csv`
- Syncs property insights to Elysia memory
- Provides investment recommendations
- Can start Hestia if not running

---

## 📋 Configuration

### Memory Storage Config

```python
from memory_storage_config import MemoryStorageConfig

# Configure for F: drive
config = MemoryStorageConfig(thumb_drive="F:", fallback_local=True)

# Get file paths
memory_file = config.get_memory_file_path()
trust_file = config.get_trust_file_path()
tasks_file = config.get_tasks_file_path()
```

### Hestia Bridge Config

```python
from hestia_bridge import HestiaBridge

bridge = HestiaBridge({
    "hestia_path": r"C:\Users\mrnat\Hestia",
    "api_url": "http://localhost:8501"
})

# Check if Hestia is running
if bridge.check_hestia_running():
    # Get property data
    properties = bridge.get_property_data(limit=100)
    
    # Get investment insights
    for prop in properties:
        insights = bridge.get_investment_insights(prop)
        print(f"{prop['address']}: {insights['recommendation']}")
```

---

## 🔄 Data Flow

### Elysia → Hestia
- Elysia can send property analysis requests
- Writes to `Hestia/data/elysia_request_*.json`
- Hestia processes and updates outputs

### Hestia → Elysia
- Hestia writes property data to `outputs/scored_listings.csv`
- Elysia reads and syncs to memory
- Properties stored with category "real_estate"
- Investment scores and metrics preserved

---

## 🛠️ Troubleshooting

### F: Drive Not Detected
- **Check**: Is thumb drive plugged in?
- **Check**: Is it mounted as F:?
- **Fallback**: System will use local storage automatically
- **Manual**: Change `thumb_drive="F:"` to another drive letter

### Hestia Not Connecting
- **Check**: Is Hestia running? (`http://localhost:8501`)
- **Start**: Run `START_HESTIA_PRO.bat` in Hestia folder
- **Verify**: Check `hestia_bridge.get_status()`

### Memory Files Not Found
- **Check**: Does `F:/ElysiaMemory/` exist?
- **Check**: Write permissions on F: drive
- **Create**: System will create directory automatically
- **Backup**: Check `F:/ElysiaMemory/backups/` for backups

---

## 📊 Status Monitoring

### Check System Status

```python
from run_elysia_unified import UnifiedElysiaSystem

system = UnifiedElysiaSystem()
status = system.get_status()

print(f"Storage: {status['components']}")
print(f"Hestia: {system.modules.get('hestia_bridge', {}).get_status()}")
```

### Check Hestia Status

```python
from hestia_bridge import HestiaBridge

bridge = HestiaBridge()
status = bridge.get_status()

print(f"Connected: {status['connected']}")
print(f"Data Available: {status['data_available']}")
print(f"Properties: {len(bridge.get_property_data() or [])}")
```

---

## 🎯 Next Steps

1. **Test Integration**: Run unified system and verify Hestia connection
2. **Sync Data**: Let Elysia sync property data from Hestia
3. **Monitor**: Check memory files on F: drive
4. **Backup**: System creates automatic backups

---

## 📝 Notes

- **F: Drive**: Primary storage location for all Elysia memory
- **Hestia**: Real estate platform runs independently on port 8501
- **Integration**: Bridge connects the two systems for data sharing
- **Fallback**: System gracefully falls back if F: unavailable

---

**Status**: ✅ Integration Complete  
**Memory Storage**: F:/ElysiaMemory/  
**Hestia Integration**: Active

