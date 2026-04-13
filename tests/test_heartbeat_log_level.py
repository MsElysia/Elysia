"""
Regression test: Verify heartbeat messages are at DEBUG level, not INFO.
Prevents heartbeat spam in logs/stdout.
"""

import pytest
import logging
from unittest.mock import Mock, patch
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_elysia_loop_heartbeat_is_debug_level(caplog):
    """Test that ElysiaLoop heartbeat uses logger.debug(), not logger.info()"""
    # Check the source file directly
    elysia_loop_file = project_root / "project_guardian" / "elysia_loop_core.py"
    assert elysia_loop_file.exists(), f"File not found: {elysia_loop_file}"
    
    with open(elysia_loop_file, 'r', encoding='utf-8') as f:
        content = f.read()
        # Find the heartbeat log line (the actual logger.debug/info call)
        lines = content.split('\n')
        heartbeat_log_lines = []
        for i, line in enumerate(lines):
            if 'ElysiaLoop heartbeat' in line and ('logger.debug' in line or 'logger.info' in line):
                heartbeat_log_lines.append((i+1, line))
        
        assert len(heartbeat_log_lines) > 0, "Heartbeat log line with logger.debug/info not found"
        for line_num, heartbeat_line in heartbeat_log_lines:
            assert 'logger.debug' in heartbeat_line, \
                f"Line {line_num}: Heartbeat should use logger.debug, found: {heartbeat_line.strip()}"
            assert 'logger.info' not in heartbeat_line, \
                f"Line {line_num}: Heartbeat should not use logger.info, found: {heartbeat_line.strip()}"


def test_monitoring_heartbeat_is_debug_level(caplog):
    """Test that monitoring heartbeat uses logger.debug(), not logger.info()"""
    try:
        from project_guardian.monitoring import Heartbeat
    except ImportError:
        pytest.skip("Heartbeat not available")
    
    # Check the source file directly
    monitoring_file = project_root / "project_guardian" / "monitoring.py"
    with open(monitoring_file, 'r', encoding='utf-8') as f:
        content = f.read()
        # Find heartbeat log lines
        heartbeat_lines = [line for line in content.split('\n') if '[Heartbeat] Tick' in line or 'Heartbeat' in line]
        
        # Check that heartbeat tick uses logger.debug
        tick_lines = [line for line in heartbeat_lines if 'Tick' in line]
        if tick_lines:
            assert any('logger.debug' in line for line in tick_lines), \
                f"Heartbeat Tick should use logger.debug, found: {tick_lines}"


def test_no_heartbeat_info_level_logs(caplog):
    """Test that no heartbeat messages appear at INFO level when logging is set to INFO"""
    # This is a runtime test - if heartbeat uses logger.debug, it won't appear at INFO level
    with caplog.at_level(logging.INFO):
        # Import modules that might log heartbeat
        try:
            from project_guardian.elysia_loop_core import ElysiaLoopCore
            from project_guardian.monitoring import Heartbeat
        except ImportError:
            pytest.skip("Required modules not available")
        
        # The actual test: if heartbeat uses logger.debug, caplog at INFO level won't capture it
        # This is verified by checking the source code in the previous tests
        # But we can also verify that no INFO-level heartbeat messages exist in the codebase
        
        elysia_loop_file = project_root / "project_guardian" / "elysia_loop_core.py"
        monitoring_file = project_root / "project_guardian" / "monitoring.py"
        
        for file_path in [elysia_loop_file, monitoring_file]:
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Check that no logger.info contains heartbeat
                    lines = content.split('\n')
                    for i, line in enumerate(lines, 1):
                        if 'logger.info' in line and 'heartbeat' in line.lower():
                            pytest.fail(f"Found logger.info with heartbeat at {file_path}:{i}: {line.strip()}")
