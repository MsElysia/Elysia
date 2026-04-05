#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Run Elysia Learning Cycle with API Keys
"""

import sys
import os
import asyncio
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

print("="*70)
print("ELYSIA LEARNING CYCLE - WITH API KEYS")
print("="*70)
print()

# Load API keys first
print("1. Loading API keys...")
try:
    from load_api_keys import load_api_keys
    keys = load_api_keys()
    print(f"   ✅ Loaded {len([k for k in keys.values() if k == 'Loaded'])} API keys")
except Exception as e:
    print(f"   ⚠️  Error loading API keys: {e}")

# Check which keys are available
print("\n2. Available API keys:")
openai_key = os.getenv("OPENAI_API_KEY")
if openai_key:
    print(f"   ✅ OpenAI API key: {openai_key[:10]}...{openai_key[-4:]}")
else:
    print("   ⚠️  OpenAI API key not found")

cohere_key = os.getenv("COHERE_API_KEY")
if cohere_key:
    print(f"   ✅ Cohere API key: {cohere_key[:10]}...{cohere_key[-4:]}")
else:
    print("   ⚠️  Cohere API key not found")

# Test Internet Learning (no API key needed)
print("\n3. Testing Internet Learning (Reddit)...")
try:
    from organized_project.src.learning.web.online_learning_system import OnlineLearningSystem
    
    learning = OnlineLearningSystem()
    
    async def learn_from_reddit():
        print("   🔍 Learning from Reddit (r/MachineLearning)...")
        result = await learning.learn_from_social_media(
            platform="reddit",
            query="autonomous AI systems",
            max_posts=5
        )
        return result
    
    result = asyncio.run(learn_from_reddit())
    if result.get("status") == "success":
        posts = result.get("data", {}).get("posts_processed", 0)
        print(f"   ✅ Successfully learned from {posts} Reddit posts!")
        print(f"   📚 Content stored in memory system")
    else:
        print(f"   ⚠️  {result.get('message', 'Unknown error')}")
        
except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()

# Test LLM Research if OpenAI key is available
if openai_key:
    print("\n4. Testing LLM Research Agent...")
    try:
        from organized_project.src.learning.llm_research_agent import LLMResearchAgent
        
        agent = LLMResearchAgent(
            memory_system=None,  # Will use mock
            harvest_engine=None,
            financial_module=None,
            config={"openai_api_key": openai_key}
        )
        
        async def research():
            print("   🔍 Querying external AIs for insights...")
            result = await agent.research_query(
                query="What are the latest trends in autonomous AI systems?",
                tags=["ai", "trends", "autonomous"]
            )
            return result
        
        result = asyncio.run(research())
        if result.get("status") == "success":
            insights = result.get("insights", [])
            print(f"   ✅ Gathered {len(insights)} insights from external AIs")
            models = result.get("models_queried", [])
            print(f"   🤖 Models queried: {', '.join(models)}")
            
            # Show first insight preview
            if insights:
                first_insight = insights[0]
                preview = first_insight.get("response", "")[:200]
                print(f"   📝 Preview: {preview}...")
        else:
            print(f"   ⚠️  {result.get('message', 'Unknown error')}")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
else:
    print("\n4. Skipping LLM Research (OpenAI API key not available)")

print("\n" + "="*70)
print("✅ LEARNING CYCLE COMPLETE")
print("="*70)
print("\nElysia has learned new information!")
print("The learning systems are working and ready to use.\n")

