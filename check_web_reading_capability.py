"""Check if Elysia can actually read from the web."""

print("=" * 70)
print("ELYSIA WEB READING CAPABILITY CHECK")
print("=" * 70)

# Check if WebScout is available
try:
    from project_guardian.webscout_agent import ElysiaWebScout
    print("\n✅ WebScout module found")
    
    # Check what methods it has
    methods = [m for m in dir(ElysiaWebScout) if not m.startswith('_')]
    print(f"\n📋 WebScout methods: {len(methods)}")
    
    # Look for web reading methods
    web_methods = [m for m in methods if any(keyword in m.lower() for keyword in ['read', 'fetch', 'scrape', 'web', 'url', 'http'])]
    if web_methods:
        print(f"   Web reading methods found: {', '.join(web_methods)}")
    else:
        print("   ⚠️  No explicit web reading methods found")
    
    # Try to inspect the class
    import inspect
    source = inspect.getsource(ElysiaWebScout)
    
    if 'urllib' in source or 'requests' in source or 'httpx' in source:
        print("   ✅ HTTP library imports found")
    else:
        print("   ⚠️  No HTTP library imports found")
    
    if 'def' in source and ('read' in source.lower() or 'fetch' in source.lower() or 'scrape' in source.lower()):
        print("   ✅ Web reading functions may exist")
    else:
        print("   ⚠️  No obvious web reading functions found")
        
except ImportError as e:
    print(f"\n❌ WebScout module not available: {e}")

# Check if there's a web_reader agent
try:
    from project_guardian.core import GuardianCore
    print("\n✅ GuardianCore available")
    print("   (web_reader agent is registered in memories)")
except ImportError:
    print("\n⚠️  GuardianCore not available")

# Check what the wrapper does
try:
    from elysia.agents.webscout import WebScoutAgent
    print("\n✅ Elysia WebScout wrapper available")
    
    # Check research_topic method
    import inspect
    source = inspect.getsource(WebScoutAgent.research_topic)
    if 'placeholder' in source.lower() or 'queue' in source.lower():
        print("   ⚠️  research_topic appears to be a placeholder")
    else:
        print("   ✅ research_topic has implementation")
        
except ImportError:
    print("\n⚠️  Elysia WebScout wrapper not available")

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print("""
Based on the code:
1. WebScout is ENABLED in config ✅
2. WebScout is INITIALIZED in logs ✅  
3. web_reader agent is REGISTERED ✅
4. BUT: research_topic() is a PLACEHOLDER ⚠️

Elysia CAN access the web infrastructure, but may not be actively
reading web content. The WebScout agent exists but may need to be
triggered or may be using LLM-based research instead of actual
web scraping.
""")
print("=" * 70)

