# project_guardian/__main__.py
# Entry point for running Elysia as a package
# Usage: python -m project_guardian

import asyncio
import logging
import sys
import json
from pathlib import Path

try:
    from .system_orchestrator import SystemOrchestrator
except ImportError:
    from system_orchestrator import SystemOrchestrator

# Configure logging
try:
    from .logging_config import setup_logging, configure_module_logging
    # Will be configured with actual config after loading
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stderr)  # Use stderr to avoid contaminating interactive prompts
        ]
    )
except ImportError:
    # Fallback if logging_config not available
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stderr)  # Use stderr to avoid contaminating interactive prompts
        ]
    )
    setup_logging = None
    configure_module_logging = None

logger = logging.getLogger(__name__)


async def main():
    """Main entry point for Elysia system."""
    logger.info("Starting Elysia System...")
    
    # Validate configuration first
    try:
        from .config_validator import ConfigValidator
        validator = ConfigValidator(config_path="config/guardian_config.json")
        validation_results = validator.validate_all()
        
        if not validation_results["valid"]:
            logger.error("Configuration validation failed:")
            for error in validation_results["errors"]:
                logger.error(f"  {error['component']}: {error['message']}")
                if error.get("suggestion"):
                    logger.error(f"    -> {error['suggestion']}")
            
            logger.error("\nRun 'python setup_guardian.py' to configure the system.")
            return 1
    except ImportError:
        logger.warning("ConfigValidator not available, skipping validation")
    except Exception as e:
        logger.warning(f"Configuration validation skipped: {e}")
    
    # Load configuration from file if available
    config = {}
    config_path = Path("config/guardian_config.json")
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
                config.update(file_config)
                logger.info(f"Loaded configuration from {config_path}")
        except Exception as e:
            logger.warning(f"Failed to load config file: {e}")
    
    # Configure logging if available
    if configure_module_logging:
        configure_module_logging(config)
        logger.info("Logging configured from config file")
    elif setup_logging:
        log_level = config.get("log_level", "INFO")
        setup_logging(log_level=log_level, log_file="guardian.log", log_dir="logs")
        logger.info(f"Logging configured (level: {log_level})")
    
    # Set defaults (memory_path is legacy alias; resolver normalizes to memory_filepath)
    config.setdefault("memory_path", "data/guardian_memory.json")
    config.setdefault("persona_path", "data/personas.json")
    config.setdefault("conversation_path", "data/conversation_context.json")
    config.setdefault("heartbeat_path", "data/heartbeat.json")
    
    # Load API keys from config
    api_keys = config.get("api_keys", {})
    if "openai_api_key" in api_keys:
        config["openai_api_key"] = api_keys["openai_api_key"]
    if "claude_api_key" in api_keys:
        config["claude_api_key"] = api_keys["claude_api_key"]
    
    orchestrator = SystemOrchestrator(config=config)
    
    try:
        # Initialize system
        success = await orchestrator.initialize()
        if not success:
            logger.error("Failed to initialize system")
            return 1
        
        # Start system
        await orchestrator.start()
        
        # Keep running
        logger.info("Elysia is running. Press Ctrl+C to shutdown.")
        
        try:
            while orchestrator._running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutdown requested...")
        
        # Shutdown gracefully
        await orchestrator.shutdown()
        
        return 0
        
    except Exception as e:
        logger.error(f"System error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

