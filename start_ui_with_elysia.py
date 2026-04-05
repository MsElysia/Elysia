#!/usr/bin/env python3
"""
Start Elysia System with UI Control Panel
Usage: python start_ui_with_elysia.py
"""

import asyncio
import sys
import logging
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

async def main():
    """Start Elysia with UI Control Panel."""
    try:
        from project_guardian.system_orchestrator import SystemOrchestrator
        
        # Configuration with UI enabled
        config = {
            "ui_enabled": True,
            "ui_host": "127.0.0.1",
            "ui_port": 5000,
            "memory_path": "data/guardian_memory.json",
            "persona_path": "data/personas.json",
            "conversation_path": "data/conversation_context.json",
            "heartbeat_path": "data/heartbeat.json",
            "timeline_db_path": "data/timeline_memory.db"
        }
        
        logger.info("=" * 60)
        logger.info("Starting Elysia System with UI Control Panel")
        logger.info("=" * 60)
        
        orchestrator = SystemOrchestrator(config=config)
        
        # Initialize system
        success = await orchestrator.initialize()
        if not success:
            logger.error("Failed to initialize system")
            return 1
        
        # Start system (includes UI)
        await orchestrator.start()
        
        logger.info("=" * 60)
        logger.info("Elysia System is running!")
        if orchestrator.ui_control_panel:
            logger.info(f"🌐 UI Control Panel: http://{orchestrator.ui_control_panel.host}:{orchestrator.ui_control_panel.port}")
        logger.info("Press Ctrl+C to shutdown")
        logger.info("=" * 60)
        
        # Keep running
        try:
            while orchestrator._running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutdown requested...")
        
        # Shutdown gracefully
        await orchestrator.shutdown()
        return 0
        
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

