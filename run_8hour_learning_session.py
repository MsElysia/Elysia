#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Elysia 8-Hour Autonomous Learning Session
Runs continuous learning cycles for 8 hours, learning from multiple sources
"""

import sys
import os
import asyncio
import time
from pathlib import Path
from datetime import datetime, timedelta
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('elysia_learning_session.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ElysiaLearningSession")

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Load API keys
try:
    from load_api_keys import load_api_keys
    load_api_keys()
    logger.info("✅ API keys loaded")
except Exception as e:
    logger.warning(f"Could not load API keys: {e}")

# Import learning systems
try:
    from organized_project.src.learning.elysia_complete_learning_system import ElysiaCompleteLearningSystem
    from organized_project.src.learning.web.online_learning_system import OnlineLearningSystem
    LEARNING_AVAILABLE = True
except ImportError as e:
    logger.error(f"Could not import learning systems: {e}")
    LEARNING_AVAILABLE = False

# Import GuardianCore for memory
try:
    from project_guardian.core import GuardianCore
    GUARDIAN_AVAILABLE = True
except ImportError:
    GUARDIAN_AVAILABLE = False
    logger.warning("GuardianCore not available, using mock memory")


class MockMemorySystem:
    """Mock memory system"""
    def remember(self, content, category="learning", tags=None, metadata=None):
        logger.info(f"📝 Stored: {content[:100]}...")
        return {"status": "success"}
    
    def recall_last(self, count=5):
        return []


class LearningSession:
    """8-hour autonomous learning session"""
    
    def __init__(self, duration_hours=8):
        self.duration_hours = duration_hours
        self.start_time = None
        self.end_time = None
        self.cycle_count = 0
        self.total_insights = 0
        self.total_articles = 0
        self.total_reddit_posts = 0
        self.total_financial_sources = 0
        
        # Initialize memory system
        if GUARDIAN_AVAILABLE:
            try:
                self.core = GuardianCore({
                    "enable_resource_monitoring": False,
                    "enable_runtime_health_monitoring": False,
                })
                self.memory_system = self.core.memory
                logger.info("✅ GuardianCore memory system initialized")
            except Exception as e:
                logger.warning(f"Could not initialize GuardianCore: {e}")
                self.memory_system = MockMemorySystem()
        else:
            self.memory_system = MockMemorySystem()
        
        # Initialize learning system
        if LEARNING_AVAILABLE:
            config = {
                "openai_api_key": os.getenv("OPENAI_API_KEY"),
                "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY"),
                "cohere_api_key": os.getenv("COHERE_API_KEY")
            }
            
            self.learning_system = ElysiaCompleteLearningSystem(
                memory_system=self.memory_system,
                harvest_engine=None,
                financial_module=None,
                config=config
            )
            logger.info("✅ Learning systems initialized")
        else:
            self.learning_system = None
    
    async def run_learning_cycle(self, cycle_num: int):
        """Run a single learning cycle"""
        logger.info(f"\n{'='*70}")
        logger.info(f"LEARNING CYCLE #{cycle_num}")
        logger.info(f"{'='*70}")
        
        cycle_results = {
            "llm_research": 0,
            "reddit_posts": 0,
            "web_articles": 0,
            "financial_sources": 0,
            "errors": []
        }
        
        try:
            # 1. Reddit Learning (every cycle)
            if self.learning_system and self.learning_system.internet_learning:
                try:
                    logger.info("🌐 Learning from Reddit...")
                    reddit_result = await self.learning_system.internet_learning.learn_from_social_media(
                        platform="reddit",
                        query="AI autonomous systems machine learning",
                        max_posts=10
                    )
                    if reddit_result.get("status") == "success":
                        posts = reddit_result.get("data", {}).get("posts_processed", 0)
                        cycle_results["reddit_posts"] = posts
                        self.total_reddit_posts += posts
                        logger.info(f"   ✅ Learned from {posts} Reddit posts")
                except Exception as e:
                    logger.error(f"   ❌ Reddit learning error: {e}")
                    cycle_results["errors"].append(f"Reddit: {str(e)}")
            
            # 2. Web Learning (every cycle)
            if self.learning_system and self.learning_system.internet_learning:
                try:
                    logger.info("🌐 Learning from web sources...")
                    web_result = await self.learning_system.internet_learning.learn_from_web(
                        sources=None,  # Use default sources
                        max_articles=10
                    )
                    if web_result.get("status") == "success":
                        articles = web_result.get("data", {}).get("articles_processed", 0)
                        cycle_results["web_articles"] = articles
                        self.total_articles += articles
                        logger.info(f"   ✅ Learned from {articles} web articles")
                except Exception as e:
                    logger.error(f"   ❌ Web learning error: {e}")
                    cycle_results["errors"].append(f"Web: {str(e)}")
            
            # 3. Financial Learning (every 2 cycles)
            if cycle_num % 2 == 0 and self.learning_system and self.learning_system.internet_learning:
                try:
                    logger.info("💰 Learning financial information...")
                    financial_result = await self.learning_system.internet_learning.learn_financial_information(
                        topics=["investment strategies", "market trends", "AI stocks", "cryptocurrency"],
                        max_sources=5
                    )
                    if financial_result.get("status") == "success":
                        sources = financial_result.get("data", {}).get("sources_processed", 0)
                        cycle_results["financial_sources"] = sources
                        self.total_financial_sources += sources
                        logger.info(f"   ✅ Learned from {sources} financial sources")
                except Exception as e:
                    logger.error(f"   ❌ Financial learning error: {e}")
                    cycle_results["errors"].append(f"Financial: {str(e)}")
            
            # 4. LLM Research (every 3 cycles, if API key available)
            if cycle_num % 3 == 0 and self.learning_system and self.learning_system.llm_research_agent:
                if os.getenv("OPENAI_API_KEY"):
                    try:
                        research_topics = [
                            "Latest trends in autonomous AI systems",
                            "Advances in machine learning and neural networks",
                            "AI safety and alignment research",
                            "Economic impact of AI automation",
                            "Future of AI development"
                        ]
                        topic = research_topics[(cycle_num // 3) % len(research_topics)]
                        
                        logger.info(f"🤖 LLM Research: {topic}")
                        research_result = await self.learning_system.llm_research_agent.research_query(
                            query=topic,
                            tags=["autonomous_learning", f"cycle_{cycle_num}"],
                            priority="medium"
                        )
                        if research_result.get("status") == "success":
                            insights = len(research_result.get("insights", []))
                            cycle_results["llm_research"] = insights
                            self.total_insights += insights
                            logger.info(f"   ✅ Gathered {insights} insights from external AIs")
                    except Exception as e:
                        logger.error(f"   ❌ LLM research error: {e}")
                        cycle_results["errors"].append(f"LLM: {str(e)}")
                else:
                    logger.info("   ⚠️  Skipping LLM research (no API key)")
            
            # 5. RSS Feed Learning (every cycle)
            if self.learning_system and self.learning_system.internet_learning:
                try:
                    logger.info("📰 Learning from RSS feeds...")
                    rss_result = await self.learning_system.internet_learning.learn_from_rss_feeds(
                        feed_urls=None  # Use default feeds
                    )
                    if rss_result.get("status") == "success":
                        entries = rss_result.get("data", {}).get("entries_processed", 0)
                        cycle_results["web_articles"] += entries
                        self.total_articles += entries
                        logger.info(f"   ✅ Learned from {entries} RSS entries")
                except Exception as e:
                    logger.error(f"   ❌ RSS learning error: {e}")
                    cycle_results["errors"].append(f"RSS: {str(e)}")
        
        except Exception as e:
            logger.error(f"❌ Error in learning cycle: {e}")
            cycle_results["errors"].append(f"General: {str(e)}")
        
        self.cycle_count += 1
        return cycle_results
    
    def print_statistics(self):
        """Print session statistics"""
        elapsed = datetime.now() - self.start_time
        elapsed_str = str(elapsed).split('.')[0]  # Remove microseconds
        
        logger.info(f"\n{'='*70}")
        logger.info("SESSION STATISTICS")
        logger.info(f"{'='*70}")
        logger.info(f"Elapsed time: {elapsed_str}")
        logger.info(f"Cycles completed: {self.cycle_count}")
        logger.info(f"Total Reddit posts learned: {self.total_reddit_posts}")
        logger.info(f"Total web articles learned: {self.total_articles}")
        logger.info(f"Total financial sources learned: {self.total_financial_sources}")
        logger.info(f"Total LLM insights gathered: {self.total_insights}")
        logger.info(f"{'='*70}\n")
    
    async def run(self):
        """Run the 8-hour learning session"""
        self.start_time = datetime.now()
        self.end_time = self.start_time + timedelta(hours=self.duration_hours)
        
        logger.info("="*70)
        logger.info("ELYSIA 8-HOUR AUTONOMOUS LEARNING SESSION")
        logger.info("="*70)
        logger.info(f"Start time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"End time: {self.end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Duration: {self.duration_hours} hours")
        logger.info("="*70)
        logger.info("\nElysia will now learn continuously for 8 hours...")
        logger.info("Learning cycles will run every 30 minutes")
        logger.info("Press Ctrl+C to stop early\n")
        
        cycle_interval = 30 * 60  # 30 minutes in seconds
        cycle_num = 1
        
        try:
            while datetime.now() < self.end_time:
                # Calculate time remaining
                remaining = self.end_time - datetime.now()
                remaining_str = str(remaining).split('.')[0]
                
                logger.info(f"\n⏰ Time remaining: {remaining_str}")
                
                # Run learning cycle
                cycle_results = await self.run_learning_cycle(cycle_num)
                
                # Print cycle summary
                logger.info(f"\n📊 Cycle #{cycle_num} Summary:")
                logger.info(f"   - Reddit posts: {cycle_results['reddit_posts']}")
                logger.info(f"   - Web articles: {cycle_results['web_articles']}")
                logger.info(f"   - Financial sources: {cycle_results['financial_sources']}")
                logger.info(f"   - LLM insights: {cycle_results['llm_research']}")
                if cycle_results['errors']:
                    logger.warning(f"   - Errors: {len(cycle_results['errors'])}")
                
                # Print overall statistics every 5 cycles
                if cycle_num % 5 == 0:
                    self.print_statistics()
                
                cycle_num += 1
                
                # Wait for next cycle (or until end time)
                if datetime.now() < self.end_time:
                    wait_time = min(cycle_interval, (self.end_time - datetime.now()).total_seconds())
                    if wait_time > 0:
                        logger.info(f"\n💤 Sleeping for {wait_time/60:.1f} minutes until next cycle...\n")
                        await asyncio.sleep(wait_time)
        
        except KeyboardInterrupt:
            logger.info("\n\n⚠️  Learning session interrupted by user")
        except Exception as e:
            logger.error(f"\n\n❌ Error in learning session: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Final statistics
            logger.info("\n" + "="*70)
            logger.info("FINAL SESSION STATISTICS")
            logger.info("="*70)
            self.print_statistics()
            
            # Get learning system statistics if available
            if self.learning_system:
                try:
                    stats = self.learning_system.get_learning_statistics()
                    logger.info("\nLearning System Statistics:")
                    if stats.get("llm_research"):
                        logger.info(f"  LLM Research queries: {stats['llm_research'].get('total_queries', 0)}")
                    if stats.get("internet_learning"):
                        internet_stats = stats["internet_learning"].get("data", {})
                        logger.info(f"  Total articles fetched: {internet_stats.get('total_articles_fetched', 0)}")
                        logger.info(f"  Total knowledge stored: {internet_stats.get('total_knowledge_stored', 0)}")
                except Exception as e:
                    logger.error(f"Error getting statistics: {e}")
            
            logger.info("\n✅ Learning session complete!")
            logger.info("All learned content has been stored in Elysia's memory system.")
            logger.info("="*70 + "\n")


async def main():
    """Main entry point"""
    session = LearningSession(duration_hours=8)
    await session.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Session stopped by user")
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()

