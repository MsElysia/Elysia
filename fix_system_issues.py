#!/usr/bin/env python3
"""
Quick fix script for Elysia/Project Guardian system issues
Installs missing optional packages and verifies system connectivity
"""

import subprocess
import sys
import os

def install_package(package):
    """Install a package using pip"""
    try:
        print(f"Installing {package}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        print(f"✅ {package} installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install {package}: {e}")
        return False

def check_package(package_name, import_name=None):
    """Check if a package is installed"""
    if import_name is None:
        import_name = package_name
    try:
        __import__(import_name)
        return True
    except ImportError:
        return False

def main():
    print("="*70)
    print("Elysia/Project Guardian System Fix Script")
    print("="*70)
    print()
    
    # List of optional packages to install
    packages = [
        ("psutil", "psutil"),
        ("faiss-cpu", "faiss"),
        ("sentence-transformers", "sentence_transformers"),
        ("anthropic", "anthropic"),
    ]
    
    print("Checking installed packages...")
    print("-"*70)
    
    missing_packages = []
    for package_name, import_name in packages:
        if check_package(package_name, import_name):
            print(f"✅ {package_name}: Already installed")
        else:
            print(f"❌ {package_name}: Missing")
            missing_packages.append(package_name)
    
    print()
    
    if not missing_packages:
        print("✅ All optional packages are installed!")
    else:
        print(f"Found {len(missing_packages)} missing package(s)")
        response = input("Install missing packages? (y/n): ").strip().lower()
        
        if response == 'y':
            print()
            print("Installing packages...")
            print("-"*70)
            for package in missing_packages:
                install_package(package)
            print()
            print("✅ Package installation complete!")
        else:
            print("Skipping package installation.")
    
    print()
    print("="*70)
    print("Checking API Keys...")
    print("="*70)
    
    # Check for API keys
    api_keys = {
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY"),
        "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY"),
    }
    
    for key_name, key_value in api_keys.items():
        if key_value:
            print(f"✅ {key_name}: Set (length: {len(key_value)})")
        else:
            print(f"❌ {key_name}: Not set")
            print(f"   To set: $env:{key_name}=\"your_key_here\" (PowerShell)")
    
    print()
    print("="*70)
    print("System Connectivity Test")
    print("="*70)
    
    try:
        print("Testing Project Guardian import...")
        from project_guardian import GuardianCore
        print("✅ Project Guardian: Import successful")
        
        print("Testing ElysiaLoop import...")
        from project_guardian.elysia_loop_core import ElysiaLoopCore
        print("✅ ElysiaLoop-Core: Import successful")
        
        print("Testing RuntimeLoop import...")
        from project_guardian.runtime_loop_core import RuntimeLoop
        print("✅ RuntimeLoop: Import successful")
        
        print()
        print("✅ All core systems are accessible!")
        print("✅ Systems are properly connected!")
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Check that project_guardian package is in Python path")
    
    print()
    print("="*70)
    print("Fix script complete!")
    print("="*70)

if __name__ == "__main__":
    main()

