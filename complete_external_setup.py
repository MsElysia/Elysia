#!/usr/bin/env python3
"""
Complete External Storage Setup
================================
Finalizes external storage setup and migrates existing memory
"""

import sys
import json
import shutil
from pathlib import Path

# Add project paths
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "project_guardian"))

# Load config
config_file = project_root / "config" / "external_storage.json"
if not config_file.exists():
    print("❌ External storage config not found. Run setup_external_memory_auto.py first.")
    sys.exit(1)

with open(config_file, 'r') as f:
    config = json.load(f)

print("="*70)
print("Completing External Storage Setup")
print("="*70)
print()

# Check for existing memory files
current_memory = project_root / "guardian_memory.json"
external_memory = Path(config["memory_filepath"])

if current_memory.exists() and not external_memory.exists():
    size_mb = current_memory.stat().st_size / (1024*1024)
    print(f"📦 Found existing memory file ({size_mb:.2f} MB)")
    print(f"🔄 Migrating to: {external_memory}")
    
    try:
        # Copy memory file
        external_memory.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(current_memory, external_memory)
        print(f"✅ Memory file migrated successfully")
        
        # Copy vector files if they exist
        current_vector_index = project_root / "memory" / "vectors" / "index.faiss"
        external_vector_index = Path(config["vector_memory_config"]["index_path"])
        
        if current_vector_index.exists():
            external_vector_index.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(current_vector_index, external_vector_index)
            print(f"✅ Vector index migrated")
        
        current_vector_metadata = project_root / "memory" / "vectors" / "metadata.json"
        external_vector_metadata = Path(config["vector_memory_config"]["metadata_path"])
        
        if current_vector_metadata.exists():
            external_vector_metadata.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(current_vector_metadata, external_vector_metadata)
            print(f"✅ Vector metadata migrated")
        
        print("\n✅ Migration complete!")
        print(f"   External storage: {config['external_drive']}")
        print(f"   Memory will now be stored on USB drive")
        print("\n💡 Original files kept as backup")
        
    except Exception as e:
        print(f"❌ Migration error: {e}")
        import traceback
        traceback.print_exc()
else:
    if external_memory.exists():
        print("✅ External memory file already exists")
    else:
        print("ℹ️  No existing memory file to migrate")
    print(f"   System will use external storage: {config['external_drive']}")

print("\n" + "="*70)
print("Setup Complete!")
print("="*70)
print("\n📁 External Storage Location: F:\\ProjectGuardian")
print("💾 Memory will be stored on USB drive (reduces system memory usage)")
print("\n🔄 Next: Restart Project Guardian to use external storage")

