#!/usr/bin/env python3
"""
Check Brave and Tavily API Status
==================================
Verifies if the search APIs are properly configured and available
"""

import sys
from pathlib import Path

# Add project paths
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "project_guardian"))

print("="*70)
print("Brave & Tavily API Status Check")
print("="*70)
print()

try:
    from project_guardian.api_key_manager import get_api_key_manager
    
    # Initialize API manager
    api_manager = get_api_key_manager()
    
    print("📋 API Key Status:")
    print()
    
    # Check Brave Search
    brave_key = api_manager.keys.brave_search
    if brave_key:
        masked = brave_key[:8] + "..." + brave_key[-4:] if len(brave_key) > 12 else "***"
        print(f"  ✅ Brave Search API: {masked}")
    else:
        print(f"  ❌ Brave Search API: Not loaded")
    
    # Check Tavily
    tavily_key = api_manager.keys.tavily
    if tavily_key:
        masked = tavily_key[:8] + "..." + tavily_key[-4:] if len(tavily_key) > 12 else "***"
        print(f"  ✅ Tavily API: {masked}")
    else:
        print(f"  ❌ Tavily API: Not loaded")
    
    print()
    print("📁 Checking API key files:")
    
    api_keys_dir = Path("API keys")
    brave_file = api_keys_dir / "brave search api key.txt"
    tavily_file = api_keys_dir / "tavily api key.txt"
    
    if brave_file.exists():
        with open(brave_file, 'r') as f:
            key = f.read().strip()
            if key:
                print(f"  ✅ brave search api key.txt: Found ({len(key)} chars)")
            else:
                print(f"  ⚠️  brave search api key.txt: Empty")
    else:
        print(f"  ❌ brave search api key.txt: Not found")
    
    if tavily_file.exists():
        with open(tavily_file, 'r') as f:
            key = f.read().strip()
            if key:
                print(f"  ✅ tavily api key.txt: Found ({len(key)} chars)")
            else:
                print(f"  ⚠️  tavily api key.txt: Empty")
    else:
        print(f"  ❌ tavily api key.txt: Not found")
    
    print()
    print("🔍 Testing WebScout Integration:")
    
    try:
        from project_guardian.webscout_agent import ElysiaWebScout
        
        webscout = ElysiaWebScout(require_api_keys=False)
        
        print(f"  ✅ ElysiaWebScout initialized")
        print(f"  📊 API Manager: {'Available' if webscout.api_manager else 'Not available'}")
        
        if webscout.api_manager:
            print(f"     - Brave Search: {'✅' if webscout.api_manager.keys.brave_search else '❌'}")
            print(f"     - Tavily: {'✅' if webscout.api_manager.keys.tavily else '❌'}")
        
        # Check usage tracking
        brave_usage = webscout.get_brave_search_usage()
        tavily_usage = webscout.get_tavily_usage()
        
        print()
        print("📊 Usage Statistics:")
        print(f"  Brave Search: {brave_usage['requests_used']}/{brave_usage['requests_limit']} ({brave_usage['percentage_used']:.1f}%)")
        print(f"  Tavily: {tavily_usage['requests_used']}/{tavily_usage['requests_limit']} ({tavily_usage['percentage_used']:.1f}%)")
        
    except Exception as e:
        print(f"  ❌ Error initializing WebScout: {e}")
        import traceback
        traceback.print_exc()
    
    print()
    print("="*70)
    print("Summary:")
    print("="*70)
    
    if brave_key and tavily_key:
        print("✅ Both APIs are configured and ready to use!")
    elif brave_key or tavily_key:
        print("⚠️  One API is configured, the other is missing")
    else:
        print("❌ Neither API is configured")
        print()
        print("To fix:")
        print("  1. Ensure API key files exist in 'API keys' folder")
        print("  2. Files should be named:")
        print("     - 'brave search api key.txt'")
        print("     - 'tavily api key.txt'")
        print("  3. Each file should contain only the API key (no extra text)")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

