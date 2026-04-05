# project_guardian/logging_config.py
# Logging Configuration: Production-ready logging setup

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional, Dict, Any

# Default log levels
DEFAULT_LOG_LEVEL = logging.INFO
DEFAULT_FILE_LOG_LEVEL = logging.DEBUG


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    log_dir: str = "logs",
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    console_output: bool = True,
    file_output: bool = True
) -> logging.Logger:
    """
    Setup production-ready logging configuration.
    
    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Log file name (defaults to guardian.log)
        log_dir: Log directory
        max_bytes: Maximum log file size before rotation
        backup_count: Number of backup log files to keep
        console_output: Enable console logging
        file_output: Enable file logging
        
    Returns:
        Configured root logger
    """
    # Parse log level
    numeric_level = getattr(logging, log_level.upper(), DEFAULT_LOG_LEVEL)
    
    # Create log directory
    if file_output and log_dir:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Remove existing handlers
    root_logger.handlers.clear()
    
    # Console handler (use stderr to avoid contaminating interactive prompts)
    if console_output:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(numeric_level)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
    
    # File handler with rotation
    if file_output and log_dir:
        log_filename = log_file or "guardian.log"
        log_filepath = log_path / log_filename
        
        file_handler = RotatingFileHandler(
            log_filepath,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(DEFAULT_FILE_LOG_LEVEL)  # More verbose in files
        
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
    
    # Suppress noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # Reduce httpx INFO spam
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger for a specific module."""
    return logging.getLogger(name)


def configure_module_logging(config: Dict[str, Any]) -> logging.Logger:
    """
    Configure logging from configuration dictionary.
    
    Args:
        config: Configuration dictionary with logging settings
        
    Returns:
        Configured root logger
    """
    log_config = config.get("logging", {})
    
    return setup_logging(
        log_level=log_config.get("level", "INFO"),
        log_file=log_config.get("file"),
        log_dir=log_config.get("directory", "logs"),
        max_bytes=log_config.get("max_bytes", 10 * 1024 * 1024),
        backup_count=log_config.get("backup_count", 5),
        console_output=log_config.get("console", True),
        file_output=log_config.get("file_output", True)
    )


# Example usage
if __name__ == "__main__":
    # Setup logging
    logger = setup_logging(
        log_level="INFO",
        log_file="guardian.log",
        log_dir="logs"
    )
    
    logger.info("Logging configured successfully")
    logger.debug("This is a debug message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")

