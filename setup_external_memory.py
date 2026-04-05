#!/usr/bin/env python3
"""
Quick Setup for External Memory Storage
=======================================
Simple script to configure Project Guardian to use external USB drive for memory
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
    print("External Memory Storage Setup")
    print("="*70)
    print()
    
    # Detect drives
    print("🔍 Detecting external drives...")
    drives = detect_removable_drives()
    
    if not drives:
        print("\n❌ No external drives found!")
        print("\nPlease:")
        print("  1. Connect your 32GB USB drive")
        print("  2. Wait for Windows to recognize it")
        print("  3. Run this script again")
        input("\nPress Enter to exit...")
        sys.exit(1)
    
    # Show available drives
    print(f"\n✅ Found {len(drives)} drive(s):\n")
    for i, drive in enumerate(drives, 1):
        marker = " 👈 RECOMMENDED" if drive['free_gb'] >= 10 else ""
        print(f"  [{i}] {drive['mountpoint']} - {drive['free_gb']} GB free{marker}")
    
    # Auto-select best drive or let user choose
    if len(drives) == 1:
        selected = drives[0]
        print(f"\n✅ Auto-selected: {selected['mountpoint']}")
    else:
        best = drives[0]  # Already sorted by free space
        print(f"\n💡 Best option: {best['mountpoint']} ({best['free_gb']} GB free)")
        choice = input(f"Use this drive? (y/n, or enter number 1-{len(drives)}): ").strip().lower()
        
        if choice == 'y' or choice == '':
            selected = best
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(drives):
                selected = drives[idx]
            else:
                print("Invalid choice, using best option")
                selected = best
        else:
            print("Using best option")
            selected = best
    
    # Setup storage
    print(f"\n📁 Setting up storage on {selected['mountpoint']}...")
    paths = setup_external_memory_storage(selected['mountpoint'])
    
    # Check for existing memory files
    current_memory = project_root / "guardian_memory.json"
    current_vector_index = project_root / "memory" / "vectors" / "index.faiss"
    current_vector_metadata = project_root / "memory" / "vectors" / "metadata.json"
    
    # Migrate if files exist
    if current_memory.exists():
        print(f"\n📦 Found existing memory file ({current_memory.stat().st_size / (1024*1024):.2f} MB)")
        migrate = input("Migrate existing memory to external drive? (y/n): ").strip().lower()
        
        if migrate == 'y':
            print("\n🔄 Migrating...")
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
    
    print(f"\n✅ Configuration saved to: {config_file}")
    print(f"\n📁 External storage location: {paths['base']}")
    print(f"   Memory file: {paths['memory_file']}")
    print(f"   Vector index: {paths['vector_index']}")
    
    print("\n" + "="*70)
    print("Setup Complete!")
    print("="*70)
    print("\nThe system will now use external storage for memory.")
    print("Restart Project Guardian to apply changes.")
    print("\n💡 Tip: Keep the USB drive connected while using the system.")
    
    input("\nPress Enter to exit...")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
    input("\nPress Enter to exit...")
    sys.exit(1)

