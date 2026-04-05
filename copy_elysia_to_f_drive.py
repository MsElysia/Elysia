#!/usr/bin/env python3
"""
Copy Elysia to F: Drive
Creates a portable, self-contained Elysia installation on thumb drive
"""

import os
import shutil
import json
from pathlib import Path
from datetime import datetime

def copy_elysia_to_f_drive():
    """Copy all Elysia files to F: drive"""
    print("="*70)
    print("COPYING ELYSIA TO F: DRIVE")
    print("="*70)
    
    # Check F: drive
    f_drive = Path("F:/")
    if not f_drive.exists():
        print("[X] F: drive not detected!")
        print("  Please plug in your thumb drive and ensure it's mounted as F:")
        return False
    
    print("[OK] F: drive detected")
    
    # Create Elysia directory on F: drive
    elysia_dir = f_drive / "Elysia"
    elysia_dir.mkdir(exist_ok=True)
    print(f"[OK] Created: {elysia_dir}")
    
    # Directories to copy
    source_dir = Path(".")
    dirs_to_copy = [
        "core_modules",
        "project_guardian",
        "config",
        "scripts",
        "old modules",
    ]
    
    # Files to copy
    files_to_copy = [
        "run_elysia.py",
        "run_elysia_unified.py",
        "run_elysia_trial_until_7am.py",
        "run_guardian.py",
        "chat_with_elysia.py",
        "interactive_elysia.py",
        "requirements.txt",
        "README.md",
        "START_ELYSIA.bat",
        "START_ELYSIA_UNIFIED.bat",
        "START_TRIAL_NOW.bat",
        "RUN_TRIAL_UNTIL_7AM.bat",
        "verify_f_drive_memory.py",
    ]
    
    # Copy directories
    print("\nCopying directories...")
    for dir_name in dirs_to_copy:
        source = source_dir / dir_name
        if source.exists():
            dest = elysia_dir / dir_name
            print(f"  Copying {dir_name}...")
            try:
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(source, dest, ignore=shutil.ignore_patterns(
                    '*.pyc', '__pycache__', '*.log', '.git', '.venv', 'venv',
                    '*.db', '*.bak', '*.tmp', 'node_modules', '.idea', '.vscode'
                ))
                print(f"    [OK] Copied: {dir_name}")
            except Exception as e:
                print(f"    [ERROR] Failed to copy {dir_name}: {e}")
        else:
            print(f"    [SKIP] {dir_name} not found")
    
    # Copy files
    print("\nCopying files...")
    copied_files = 0
    for file_name in files_to_copy:
        source = source_dir / file_name
        if source.exists():
            dest = elysia_dir / file_name
            try:
                shutil.copy2(source, dest)
                print(f"  [OK] {file_name}")
                copied_files += 1
            except Exception as e:
                print(f"  [ERROR] {file_name}: {e}")
        else:
            print(f"  [SKIP] {file_name} not found")
    
    # Copy documentation files
    print("\nCopying documentation...")
    doc_files = list(source_dir.glob("*.md"))
    doc_copied = 0
    for doc_file in doc_files:
        if doc_file.name not in ["README.md"]:  # Already copied
            try:
                dest = elysia_dir / doc_file.name
                shutil.copy2(doc_file, dest)
                doc_copied += 1
            except Exception as e:
                print(f"  [ERROR] {doc_file.name}: {e}")
    print(f"  [OK] Copied {doc_copied} documentation files")
    
    # Create memory directory structure
    memory_dir = elysia_dir / "ElysiaMemory"
    memory_dir.mkdir(exist_ok=True)
    backups_dir = memory_dir / "backups"
    backups_dir.mkdir(exist_ok=True)
    print(f"\n[OK] Created memory directory: {memory_dir}")
    
    # Copy existing memory files if they exist
    existing_memory = f_drive / "ElysiaMemory"
    if existing_memory.exists():
        print("\nCopying existing memory files...")
        for mem_file in existing_memory.glob("*.json"):
            try:
                shutil.copy2(mem_file, memory_dir / mem_file.name)
                print(f"  [OK] {mem_file.name}")
            except Exception as e:
                print(f"  [ERROR] {mem_file.name}: {e}")
    
    # Create launcher script for F: drive
    launcher_bat = elysia_dir / "START_ELYSIA_F_DRIVE.bat"
    launcher_content = f"""@echo off
cd /d "%~dp0"
echo ========================================
echo Elysia - Running from F: Drive
echo ========================================
echo.
echo Memory Location: F:\\Elysia\\ElysiaMemory\\
echo.
python run_elysia_unified.py
pause
"""
    launcher_bat.write_text(launcher_content)
    print(f"\n[OK] Created launcher: {launcher_bat}")
    
    # Create README for F: drive
    readme_path = elysia_dir / "README_F_DRIVE.txt"
    readme_content = f"""Elysia - Portable Installation
=============================

This is a portable installation of Elysia on your thumb drive.

LOCATION: F:\\Elysia\\

QUICK START:
1. Double-click: START_ELYSIA_F_DRIVE.bat
2. Elysia will run using memory from F:\\Elysia\\ElysiaMemory\\

MEMORY STORAGE:
- All memories stored in: F:\\Elysia\\ElysiaMemory\\
- Backups in: F:\\Elysia\\ElysiaMemory\\backups\\
- Portable - plug into any computer and run!

REQUIREMENTS:
- Python 3.8+ installed on target computer
- Dependencies: pip install -r requirements.txt

FILES INCLUDED:
- Core modules and systems
- All Elysia components
- Configuration files
- Documentation
- Launcher scripts

Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

To use on another computer:
1. Plug thumb drive into new computer
2. Ensure it's mounted as F: drive
3. Run START_ELYSIA_F_DRIVE.bat
4. Elysia will continue from where she left off!
"""
    readme_path.write_text(readme_content)
    print(f"[OK] Created README: {readme_path}")
    
    # Create config file for F: drive
    config_file = elysia_dir / "elysia_f_drive_config.json"
    config_content = {
        "storage_path": str(memory_dir),
        "thumb_drive": "F:",
        "portable": True,
        "memory_file": str(memory_dir / "guardian_memory.json"),
        "trust_file": str(memory_dir / "enhanced_trust.json"),
        "tasks_file": str(memory_dir / "enhanced_tasks.json"),
        "created": datetime.now().isoformat()
    }
    with open(config_file, 'w') as f:
        json.dump(config_content, f, indent=2)
    print(f"[OK] Created config: {config_file}")
    
    # Summary
    print("\n" + "="*70)
    print("COPY COMPLETE")
    print("="*70)
    print(f"\nElysia copied to: {elysia_dir}")
    print(f"Memory location: {memory_dir}")
    print(f"\nFiles copied: {copied_files} files + {doc_copied} docs")
    print(f"Directories copied: {len([d for d in dirs_to_copy if (source_dir / d).exists()])}")
    print("\nTo run Elysia from F: drive:")
    print(f"  Double-click: {elysia_dir}\\START_ELYSIA_F_DRIVE.bat")
    print("\n" + "="*70)
    
    return True

if __name__ == "__main__":
    copy_elysia_to_f_drive()




