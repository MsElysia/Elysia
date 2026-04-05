#!/usr/bin/env python3
"""
Migrate Memory to External Storage
==================================
Interactive script to migrate Project Guardian memory to external USB drive
"""

import sys
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
    print("Project Guardian - External Storage Migration")
    print("="*70)
    print()
    
    # Detect external drives
    print("Scanning for external drives...")
    drives = detect_removable_drives()
    
    if not drives:
        print("❌ No external drives detected!")
        print("   Please connect a USB drive and try again.")
        sys.exit(1)
    
    print(f"\n✅ Found {len(drives)} drive(s):\n")
    for i, drive in enumerate(drives, 1):
        print(f"  [{i}] {drive['mountpoint']}")
        print(f"      Type: {drive['fstype']}")
        print(f"      Free: {drive['free_gb']} GB / {drive['total_gb']} GB")
        print(f"      Removable: {'Yes' if drive['is_removable'] else 'Unknown'}")
        print()
    
    # Let user select drive
    if len(drives) == 1:
        selected_drive = drives[0]
        print(f"Using drive: {selected_drive['mountpoint']}")
    else:
        while True:
            try:
                choice = input(f"Select drive (1-{len(drives)}): ").strip()
                idx = int(choice) - 1
                if 0 <= idx < len(drives):
                    selected_drive = drives[idx]
                    break
                else:
                    print(f"Please enter a number between 1 and {len(drives)}")
            except ValueError:
                print("Please enter a valid number")
            except KeyboardInterrupt:
                print("\nCancelled.")
                sys.exit(0)
    
    # Check free space
    if selected_drive['free_gb'] < 5.0:
        print(f"\n⚠️  Warning: Only {selected_drive['free_gb']} GB free on selected drive")
        print("   Recommended: At least 5 GB free for memory storage")
        response = input("Continue anyway? (y/n): ").strip().lower()
        if response != 'y':
            print("Cancelled.")
            sys.exit(0)
    
    # Setup external storage
    print(f"\n📁 Setting up storage on {selected_drive['mountpoint']}...")
    paths = setup_external_memory_storage(selected_drive['mountpoint'])
    
    # Find current memory files
    current_memory = project_root / "guardian_memory.json"
    current_vector_index = project_root / "memory" / "vectors" / "index.faiss"
    current_vector_metadata = project_root / "memory" / "vectors" / "metadata.json"
    
    files_to_migrate = []
    if current_memory.exists():
        files_to_migrate.append(("Memory file", current_memory))
    if current_vector_index.exists():
        files_to_migrate.append(("Vector index", current_vector_index))
    if current_vector_metadata.exists():
        files_to_migrate.append(("Vector metadata", current_vector_metadata))
    
    if not files_to_migrate:
        print("\n⚠️  No memory files found to migrate")
        print(f"   External storage is ready at: {paths['base']}")
        print("   The system will use external storage for new memories.")
        sys.exit(0)
    
    print(f"\n📦 Files to migrate ({len(files_to_migrate)}):")
    for name, path in files_to_migrate:
        size_mb = path.stat().st_size / (1024 * 1024)
        print(f"   - {name}: {path.name} ({size_mb:.2f} MB)")
    
    # Confirm migration
    print("\n⚠️  This will copy memory files to the external drive.")
    print("   Original files will be kept as backup.")
    response = input("\nProceed with migration? (y/n): ").strip().lower()
    
    if response != 'y':
        print("Cancelled.")
        sys.exit(0)
    
    # Perform migration
    print("\n🔄 Migrating memory files...")
    success = migrate_memory_to_external(
        source_memory_file=str(current_memory),
        external_paths=paths,
        source_vector_index=str(current_vector_index) if current_vector_index.exists() else None,
        source_vector_metadata=str(current_vector_metadata) if current_vector_metadata.exists() else None
    )
    
    if success:
        print("\n✅ Migration completed successfully!")
        print(f"\n📁 External storage location: {paths['base']}")
        print("\n📝 Next steps:")
        print("   1. Update your config to use external storage paths:")
        print(f"      memory_filepath: \"{paths['memory_file']}\"")
        print(f"      vector_memory_config:")
        print(f"        index_path: \"{paths['vector_index']}\"")
        print(f"        metadata_path: \"{paths['vector_metadata']}\"")
        print("\n   2. Restart the system to use external storage")
        print("\n   3. Original files are kept as backup")
    else:
        print("\n❌ Migration failed. Check logs for details.")
        sys.exit(1)
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

