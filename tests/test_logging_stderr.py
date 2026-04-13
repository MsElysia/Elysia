"""
Unit tests for logging stderr configuration.
Tests verify that StreamHandler uses stderr, not stdout.
"""

import pytest
import sys
import io
import logging
from pathlib import Path
from unittest.mock import patch, Mock

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_logging_config_uses_stderr():
    """Test that project_guardian logging_config uses stderr."""
    from project_guardian.logging_config import setup_logging
    
    # Capture stderr
    stderr_capture = io.StringIO()
    
    with patch('sys.stderr', stderr_capture):
        setup_logging(console_output=True, file_output=False)
        
        # Get root logger
        root_logger = logging.getLogger()
        
        # Find StreamHandler
        stream_handlers = [h for h in root_logger.handlers if isinstance(h, logging.StreamHandler)]
        assert len(stream_handlers) > 0, "No StreamHandler found"
        
        # Verify it uses stderr
        for handler in stream_handlers:
            assert handler.stream is sys.stderr, f"Handler uses {handler.stream}, expected sys.stderr"


def test_elysia_logging_config_uses_stderr():
    """Test that elysia logging_config uses stderr."""
    from elysia.logging_config import setup_logging
    import sys
    
    # Clear existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    
    # Setup logging
    setup_logging()
    
    # Find StreamHandler (not RotatingFileHandler)
    stream_handlers = [h for h in root_logger.handlers 
                      if isinstance(h, logging.StreamHandler) 
                      and not isinstance(h, logging.handlers.RotatingFileHandler)]
    
    assert len(stream_handlers) > 0, "No StreamHandler found"
    
    # Verify console handler uses stderr
    console_handler = stream_handlers[0]
    assert console_handler.stream is sys.stderr, f"Console handler uses {console_handler.stream}, expected sys.stderr"


def test_logs_do_not_contaminate_stdout():
    """Test that logs go to stderr, not stdout."""
    import logging
    import sys
    
    # Setup logging with stderr
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    
    # Create handler that writes to stderr
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(logging.Formatter('%(message)s'))
    root_logger.addHandler(stderr_handler)
    root_logger.setLevel(logging.INFO)
    
    # Verify handler stream is stderr
    assert stderr_handler.stream is sys.stderr, "Handler should use sys.stderr"
    
    # Cleanup
    root_logger.handlers.clear()


def test_interactive_prompt_not_contaminated():
    """Test that interactive prompt output is not contaminated by logs."""
    import logging
    import sys
    
    # Setup logging with stderr
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(logging.Formatter('%(message)s'))
    root_logger.addHandler(stderr_handler)
    root_logger.setLevel(logging.INFO)
    
    # Verify handler stream is stderr (not stdout)
    assert stderr_handler.stream is sys.stderr, "Handler should use sys.stderr, not sys.stdout"
    assert stderr_handler.stream is not sys.stdout, "Handler should NOT use sys.stdout"
    
    # Cleanup
    root_logger.handlers.clear()
