"""
Run Elysia Learning Cycle
Initializes learning systems and runs an autonomous learning cycle
"""

import sys
import os
import asyncio
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Load API keys
try:
    from load_api_keys import load_api_keys
    load_api_keys()
    print("✅ API keys loaded")
except ImportError:
    print("⚠️  load_api_keys.py not found, using environment variables")

# Import GuardianCore for memory system
try:
    from project_guardian.core import GuardianCore
    GUARDIAN_CORE_AVAILABLE = True
except ImportError:
    print("⚠️  GuardianCore not available, using mock memory system")
    GUARDIAN_CORE_AVAILABLE = False

# Import learning systems
try:
    from organized_project.src.learning.elysia_complete_learning_system import ElysiaCompleteLearningSystem
    LEARNING_SYSTEM_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Could not import learning systems: {e}")
    LEARNING_SYSTEM_AVAILABLE = False


class MockMemorySystem:
    """Mock memory system for testing"""
    def remember(self, content, category="learning", tags=None, metadata=None):
        print(f"  📝 Stored: {content[:100]}...")
        return {"status": "success"}
    
    def recall_last(self, count=5):
        return []


async def run_learning_cycle():
    """Run a complete learning cycle"""
    print("\n" + "="*70)
    print("ELYSIA LEARNING CYCLE")
    print("="*70 + "\n")
    
    # Initialize memory system
    print("1. Initializing memory system...")
    if GUARDIAN_CORE_AVAILABLE:
        try:
            core = GuardianCore({
                "enable_resource_monitoring": False,
                "enable_runtime_health_monitoring": False,
            })
            memory_system = core.memory
            print("   ✅ GuardianCore memory system initialized")
        except Exception as e:
            print(f"   ⚠️  Could not initialize GuardianCore: {e}")
            memory_system = MockMemorySystem()
            print("   ✅ Using mock memory system")
    else:
        memory_system = MockMemorySystem()
        print("   ✅ Using mock memory system")
    
    # Initialize learning system
    if not LEARNING_SYSTEM_AVAILABLE:
        print("\n❌ Learning systems not available. Please check imports.")
        return
    
    print("\n2. Initializing learning systems...")
    try:
        config = {
            "openai_api_key": os.getenv("OPENAI_API_KEY"),
            "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY")
        }
        
        learning_system = ElysiaCompleteLearningSystem(
            memory_system=memory_system,
            harvest_engine=None,  # Optional
            financial_module=None,  # Optional
            config=config
        )
        print("   ✅ Learning systems initialized")
    except Exception as e:
        print(f"   ❌ Error initializing learning systems: {e}")
        return
    
    # Run learning cycles
    print("\n3. Running learning cycles...\n")
    
    # Cycle 1: Autonomous learning
    print("📚 Cycle 1: Autonomous Learning (Complex Topic)")
    print("-" * 70)
    try:
        result1 = await learning_system.autonomous_learning_cycle(
            complexity_score=0.8,
            uncertainty_score=0.7,
            financial_relevance=True
        )
        print(f"   ✅ LLM Research: {result1.get('llm_research', {}).get('status', 'N/A')}")
        print(f"   ✅ Internet Learning: {result1.get('internet_learning', {}).get('status', 'N/A')}")
        print(f"   ✅ Reddit Learning: {result1.get('reddit_learning', {}).get('status', 'N/A')}")
        print(f"   ✅ Financial Learning: {result1.get('financial_learning', {}).get('status', 'N/A')}")
    except Exception as e:
        print(f"   ⚠️  Error in autonomous learning: {e}")
    
    # Cycle 2: Internet learning (Reddit)
    print("\n🌐 Cycle 2: Internet Learning (Reddit)")
    print("-" * 70)
    try:
        if learning_system.internet_learning:
            reddit_result = await learning_system.internet_learning.learn_from_social_media(
                platform="reddit",
                query="AI autonomous systems",
                max_posts=5
            )
            if reddit_result.get("status") == "success":
                posts = reddit_result.get("data", {}).get("posts_processed", 0)
                print(f"   ✅ Learned from {posts} Reddit posts")
            else:
                print(f"   ⚠️  {reddit_result.get('message', 'Unknown error')}")
    except Exception as e:
        print(f"   ⚠️  Error in Reddit learning: {e}")
    
    # Cycle 3: Financial learning
    print("\n💰 Cycle 3: Financial Learning")
    print("-" * 70)
    try:
        if learning_system.internet_learning:
            financial_result = await learning_system.internet_learning.learn_financial_information(
                topics=["investment strategies", "market trends"],
                max_sources=3
            )
            if financial_result.get("status") == "success":
                sources = financial_result.get("data", {}).get("sources_processed", 0)
                print(f"   ✅ Learned from {sources} financial sources")
            else:
                print(f"   ⚠️  {financial_result.get('message', 'Unknown error')}")
    except Exception as e:
        print(f"   ⚠️  Error in financial learning: {e}")
    
    # Cycle 4: LLM Research (if API key available)
    print("\n🤖 Cycle 4: LLM Research (External AI Learning)")
    print("-" * 70)
    if os.getenv("OPENAI_API_KEY"):
        try:
            if learning_system.llm_research_agent:
                research_result = await learning_system.llm_research_agent.research_query(
                    query="What are the latest trends in autonomous AI systems?",
                    tags=["ai", "trends", "autonomous"]
                )
                if research_result.get("status") == "success":
                    insights = research_result.get("insights", [])
                    print(f"   ✅ Gathered {len(insights)} insights from external AIs")
                    print(f"   ✅ Models queried: {research_result.get('models_queried', [])}")
                else:
                    print(f"   ⚠️  {research_result.get('message', 'Unknown error')}")
        except Exception as e:
            print(f"   ⚠️  Error in LLM research: {e}")
    else:
        print("   ⚠️  OpenAI API key not found - skipping LLM research")
    
    # Get statistics
    print("\n4. Learning Statistics")
    print("-" * 70)
    try:
        stats = learning_system.get_learning_statistics()
        
        if stats.get("llm_research"):
            llm_stats = stats["llm_research"]
            print(f"   📊 LLM Research:")
            print(f"      - Total queries: {llm_stats.get('total_queries', 0)}")
            print(f"      - Total insights: {llm_stats.get('total_insights', 0)}")
            print(f"      - Models used: {', '.join(llm_stats.get('models_used', []))}")
        
        if stats.get("adversarial_learning"):
            adv_stats = stats["adversarial_learning"]
            print(f"   📊 Adversarial Learning:")
            print(f"      - Total critiques: {adv_stats.get('devils_advocate', {}).get('total_critiques', 0)}")
            print(f"      - Plans challenged: {adv_stats.get('devils_advocate', {}).get('plans_challenged', 0)}")
        
        if stats.get("internet_learning"):
            internet_stats = stats["internet_learning"].get("data", {})
            print(f"   📊 Internet Learning:")
            print(f"      - Articles fetched: {internet_stats.get('total_articles_fetched', 0)}")
            print(f"      - Knowledge stored: {internet_stats.get('total_knowledge_stored', 0)}")
            print(f"      - Learning sessions: {internet_stats.get('learning_sessions_count', 0)}")
    except Exception as e:
        print(f"   ⚠️  Error getting statistics: {e}")
    
    print("\n" + "="*70)
    print("✅ LEARNING CYCLE COMPLETE")
    print("="*70 + "\n")
    print("Elysia has learned new information and stored it in memory!")
    print("You can check the memory system to see what was learned.\n")


if __name__ == "__main__":
    try:
        asyncio.run(run_learning_cycle())
    except KeyboardInterrupt:
        print("\n\n⚠️  Learning cycle interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error running learning cycle: {e}")
        import traceback
        traceback.print_exc()

