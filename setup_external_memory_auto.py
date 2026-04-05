#!/usr/bin/env python3
"""
Automatic External Memory Storage Setup
=======================================
Fully automatic setup - no user interaction required
"""

import sys
import json
from pathlib import Path

# Add project paths
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "project_guardian"))

try:
    from project_guardian.external_storage import (
        detect_removable_drives,
        setup_external_memory_storage,
        migrate_memory_to_external
    )
    
    print("="*70)
    print("Automatic External Memory Storage Setup")
    print("="*70)
    print()
    
    # Detect drives
    print("🔍 Detecting external drives...")
    drives = detect_removable_drives()
    
    if not drives:
        print("❌ No external drives found!")
        print("   Please connect your USB drive and run again.")
        sys.exit(1)
    
    # Auto-select best drive (most free space)
    selected = drives[0]
    print(f"✅ Selected drive: {selected['mountpoint']} ({selected['free_gb']} GB free)")
    
    # Setup storage
    print(f"📁 Setting up storage on {selected['mountpoint']}...")
    paths = setup_external_memory_storage(selected['mountpoint'])
    
    # Check for existing memory files
    current_memory = project_root / "guardian_memory.json"
    current_vector_index = project_root / "memory" / "vectors" / "index.faiss"
    current_vector_metadata = project_root / "memory" / "vectors" / "metadata.json"
    
    # Migrate if files exist
    if current_memory.exists():
        size_mb = current_memory.stat().st_size / (1024*1024)
        print(f"📦 Found existing memory file ({size_mb:.2f} MB)")
        print("🔄 Migrating to external storage...")
        
        success = migrate_memory_to_external(
            source_memory_file=str(current_memory),
            external_paths=paths,
            source_vector_index=str(current_vector_index) if current_vector_index.exists() else None,
            source_vector_metadata=str(current_vector_metadata) if current_vector_metadata.exists() else None
        )
        
        if success:
            print("✅ Migration completed!")
        else:
            print("⚠️  Migration had issues, but external storage is ready")
    
    # Create/update config
    config_dir = project_root / "config"
    config_dir.mkdir(exist_ok=True)
    config_file = config_dir / "external_storage.json"
    
    config = {
        "use_external_storage": True,
        "external_drive": selected['mountpoint'],
        "memory_filepath": paths["memory_file"],
        "vector_memory_config": {
            "index_path": paths["vector_index"],
            "metadata_path": paths["vector_metadata"]
        },
        "timeline_db_path": paths["timeline_db"],
        "data_dir": paths["data_dir"]
    }
    
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)
    
    print(f"✅ Configuration saved to: {config_file}")
    print(f"📁 External storage: {paths['base']}")
    print(f"   Memory: {paths['memory_file']}")
    print(f"   Vectors: {paths['vector_index']}")
    
    print("\n" + "="*70)
    print("✅ Setup Complete!")
    print("="*70)
    print("\nThe system will now use external storage for memory.")
    print("This will reduce system memory usage significantly.")
    print("\n💡 Keep the USB drive connected while using the system.")
    print("   Restart Project Guardian to apply changes.")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

