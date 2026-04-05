#!/usr/bin/env python3
"""
Load API keys from the API keys folder and set them as environment variables.
This allows Elysia to use various AI services.
"""

import os
from pathlib import Path

def load_api_keys():
    """Load API keys from the API keys folder."""
    api_keys_dir = Path(__file__).parent / "API keys"
    
    if not api_keys_dir.exists():
        print(f"[ERROR] API keys directory not found: {api_keys_dir}")
        return {}
    
    api_keys = {}
    
    # Map of file names to environment variable names
    key_mapping = {
        "chat gpt api key for elysia.txt": "OPENAI_API_KEY",
        "open router API key.txt": "OPENROUTER_API_KEY",
        "Cohere API key.txt": "COHERE_API_KEY",
        "Hugging face API key.txt": "HUGGINGFACE_API_KEY",
        "replicate API key.txt": "REPLICATE_API_KEY",
        "alpha vantage API.txt": "ALPHA_VANTAGE_API_KEY",
        "brave search api key.txt": "BRAVE_SEARCH_API_KEY",
    }
    
    for filename, env_var in key_mapping.items():
        filepath = api_keys_dir / filename
        if filepath.exists():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    key = f.read().strip()
                    if key:
                        os.environ[env_var] = key
                        api_keys[env_var] = "Loaded"
                        print(f"[OK] Loaded {env_var}")
                    else:
                        api_keys[env_var] = "Empty file"
            except Exception as e:
                api_keys[env_var] = f"Error: {e}"
                print(f"[WARN] Could not load {filename}: {e}")
        else:
            api_keys[env_var] = "File not found"
    
    return api_keys

if __name__ == "__main__":
    print("=" * 60)
    print("Loading API Keys for Elysia")
    print("=" * 60)
    print()
    
    keys = load_api_keys()
    
    print()
    print("=" * 60)
    print("Summary:")
    print("=" * 60)
    for env_var, status in keys.items():
        print(f"  {env_var}: {status}")
    
    print()
    print("[OK] API keys loaded! They are now available as environment variables.")
    print("     You can now run Elysia with AI capabilities enabled.")

