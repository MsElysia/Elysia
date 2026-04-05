#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Search Elysia's Memory for Specific Topics
Search what Elysia has learned about specific topics
"""

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

def search_knowledge(query: str):
    """Search Elysia's memory for specific topics"""
    print("="*70)
    print(f"SEARCHING ELYSIA'S KNOWLEDGE: '{query}'")
    print("="*70)
    print()
    
    try:
        from project_guardian.core import GuardianCore
        
        print("Loading memory system...")
        core = GuardianCore({
            "enable_resource_monitoring": False,
            "enable_runtime_health_monitoring": False,
        })
        memory = core.memory
        print("✅ Memory system loaded\n")
        
        # Search for query in memories
        print(f"Searching for: '{query}'...")
        print("-"*70)
        
        results = []
        
        # Try different search methods
        try:
            if hasattr(memory, 'search'):
                results = memory.search(query)
        except:
            pass
        
        # Also search recent memories
        try:
            recent = memory.recall_last(count=100)
            query_lower = query.lower()
            for mem in recent:
                content = str(mem.get('thought', mem.get('content', mem.get('memory', '')))).lower()
                if query_lower in content:
                    results.append(mem)
        except:
            pass
        
        if results:
            print(f"\n✅ Found {len(results)} results:\n")
            
            for i, mem in enumerate(results[:20], 1):  # Show first 20
                content = mem.get('thought', mem.get('content', mem.get('memory', '')))
                timestamp = mem.get('timestamp', mem.get('created_at', 'Unknown'))
                tags = mem.get('tags', [])
                
                print(f"{i}. [{timestamp}]")
                if tags:
                    print(f"   Tags: {', '.join(str(t) for t in tags[:5])}")
                print(f"   {content[:300]}...")
                print()
            
            if len(results) > 20:
                print(f"... and {len(results) - 20} more results")
        else:
            print(f"\n⚠️  No results found for '{query}'")
            print("\nTry:")
            print("  - Different keywords")
            print("  - Broader search terms")
            print("  - Check if learning session has completed")
        
        print("\n" + "="*70)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        query = input("Enter search query: ")
    
    search_knowledge(query)

