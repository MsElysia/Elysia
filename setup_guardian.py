#!/usr/bin/env python3
"""
Project Guardian Setup Wizard
Interactive setup script for first-time configuration
"""

import os
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional

def print_header():
    """Print setup header."""
    print("=" * 60)
    print("Project Guardian Setup Wizard")
    print("=" * 60)
    print()

def create_default_config() -> Dict[str, Any]:
    """Create default configuration."""
    return {
        "version": "1.0",
        "memory_path": "data/guardian_memory.json",
        "persona_path": "data/personas.json",
        "conversation_path": "data/conversation_context.json",
        "heartbeat_path": "data/heartbeat.json",
        "storage_path": "data",
        "log_level": "INFO",
        "api_keys": {}
    }

def setup_directories():
    """Create required directories."""
    print("Setting up directories...")
    
    directories = [
        "data",
        "data/backups",
        "data/vault",
        "data/snapshots",
        "config"
    ]
    
    for directory in directories:
        dir_path = Path(directory)
        if not dir_path.exists():
            dir_path.mkdir(parents=True, exist_ok=True)
            print(f"  ✓ Created {directory}/")
        else:
            print(f"  ✓ {directory}/ already exists")

def setup_api_keys(config: Dict[str, Any]) -> Dict[str, Any]:
    """Interactive API key setup."""
    print("\nAPI Key Configuration")
    print("-" * 60)
    print("Enter API keys (press Enter to skip optional keys)")
    print()
    
    # OpenAI (recommended)
    openai_key = input("OpenAI API Key (recommended): ").strip()
    if openai_key:
        config["api_keys"]["openai_api_key"] = openai_key
        os.environ["OPENAI_API_KEY"] = openai_key
        print("  ✓ OpenAI key configured")
    
    # Claude (optional)
    claude_key = input("Anthropic/Claude API Key (optional): ").strip()
    if claude_key:
        config["api_keys"]["claude_api_key"] = claude_key
        os.environ["ANTHROPIC_API_KEY"] = claude_key
        print("  ✓ Claude key configured")
    
    # Optional keys
    print("\nOptional API Keys (press Enter to skip):")
    optional_keys = {
        "GROK_API_KEY": "Grok API Key",
        "HUGGINGFACE_API_KEY": "HuggingFace API Key",
        "REPLICATE_API_KEY": "Replicate API Key"
    }
    
    for env_key, prompt in optional_keys.items():
        key_value = input(f"{prompt}: ").strip()
        if key_value:
            config["api_keys"][env_key.lower()] = key_value
            os.environ[env_key] = key_value
    
    return config

def save_config(config: Dict[str, Any], config_path: str = "config/guardian_config.json"):
    """Save configuration to file."""
    config_file = Path(config_path)
    config_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)
    
    print(f"\n✓ Configuration saved to {config_path}")
    return config_file

def validate_setup():
    """Run configuration validation."""
    print("\nValidating configuration...")
    
    try:
        from project_guardian.config_validator import ConfigValidator
        
        validator = ConfigValidator()
        results = validator.validate_all()
        
        if results["valid"]:
            print("  ✓ Configuration is valid!")
        else:
            print("  ⚠️  Configuration has issues:")
            for error in results["errors"]:
                print(f"    - {error['message']}")
                if error.get("suggestion"):
                    print(f"      → {error['suggestion']}")
        
        return results["valid"]
    except ImportError as e:
        print(f"  ⚠️  Could not import config validator: {e}")
        return True  # Don't fail setup if validator unavailable

def main():
    """Main setup function."""
    print_header()
    
    # Check if already configured
    config_file = Path("config/guardian_config.json")
    if config_file.exists():
        response = input("Configuration file already exists. Reconfigure? (y/N): ").strip().lower()
        if response != 'y':
            print("Setup cancelled.")
            return
    
    # Create directories
    setup_directories()
    
    # Create default config
    config = create_default_config()
    
    # Setup API keys
    try:
        config = setup_api_keys(config)
    except KeyboardInterrupt:
        print("\n\nSetup cancelled.")
        return
    
    # Save configuration
    config_path = save_config(config)
    
    # Validate
    is_valid = validate_setup()
    
    # Final message
    print("\n" + "=" * 60)
    if is_valid:
        print("✅ Setup complete!")
        print("\nYou can now start Project Guardian with:")
        print("  python -m project_guardian")
        print("\nOr start the UI with:")
        print("  python start_ui_panel.py")
    else:
        print("⚠️  Setup completed with warnings.")
        print("Please review the issues above before starting.")
    print("=" * 60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nSetup cancelled.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Setup failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

