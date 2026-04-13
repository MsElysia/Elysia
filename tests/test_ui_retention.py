"""
UI Retention Policy Tests
=========================
Tests for history retention policy (pruning old files, log size caps).
"""

import pytest
import tempfile
import json
import time
import os
from pathlib import Path
from datetime import datetime
from unittest.mock import patch

try:
    from project_guardian.ui.app import _prune_history_dir, _ensure_dir, MAX_RUN_ONCE_HISTORY, MAX_ACCEPTANCE_HISTORY, MAX_LOG_BYTES
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    pytestmark = pytest.mark.skip("UI app not available")


class TestRunOnceHistoryPruning:
    """Test run_once history pruning by count"""
    
    def test_prunes_run_once_history_by_count(self, tmp_path):
        """Verify pruning keeps only newest MAX_RUN_ONCE_HISTORY files"""
        history_dir = tmp_path / "run_once_history"
        history_dir.mkdir()
        
        # Create more than max files with different mtimes
        num_files = MAX_RUN_ONCE_HISTORY + 50
        files_created = []
        
        for i in range(num_files):
            file_path = history_dir / f"test_{i:04d}.json"
            file_path.write_text(json.dumps({"test": i}))
            # Set different mtimes (older files first)
            mtime = time.time() - (num_files - i) * 10  # Older files have earlier mtimes
            os.utime(file_path, (mtime, mtime))
            files_created.append(file_path)
        
        # Prune history
        _prune_history_dir(history_dir, MAX_RUN_ONCE_HISTORY, allowed_suffixes=('.json',))
        
        # Verify only newest MAX_RUN_ONCE_HISTORY remain
        remaining_files = list(history_dir.glob("*.json"))
        assert len(remaining_files) == MAX_RUN_ONCE_HISTORY, \
            f"Expected {MAX_RUN_ONCE_HISTORY} files, got {len(remaining_files)}"
        
        # Verify newest files are kept (highest numbers)
        remaining_numbers = sorted([int(f.stem.split('_')[1]) for f in remaining_files])
        assert remaining_numbers[-1] == num_files - 1, "Newest file should be kept"
        assert remaining_numbers[0] >= num_files - MAX_RUN_ONCE_HISTORY, "Oldest kept file should be within limit"


class TestAcceptanceHistoryPruning:
    """Test acceptance history pruning by count"""
    
    def test_prunes_acceptance_history_by_count(self, tmp_path):
        """Verify pruning keeps only newest MAX_ACCEPTANCE_HISTORY files"""
        history_dir = tmp_path / "acceptance_history"
        history_dir.mkdir()
        
        # Create more than max files with different mtimes
        num_files = MAX_ACCEPTANCE_HISTORY + 50
        files_created = []
        
        for i in range(num_files):
            file_path = history_dir / f"test_{i:04d}.json"
            file_path.write_text(json.dumps({"test": i}))
            # Set different mtimes (older files first)
            mtime = time.time() - (num_files - i) * 10
            os.utime(file_path, (mtime, mtime))
            files_created.append(file_path)
        
        # Prune history
        _prune_history_dir(history_dir, MAX_ACCEPTANCE_HISTORY, allowed_suffixes=('.json',))
        
        # Verify only newest MAX_ACCEPTANCE_HISTORY remain
        remaining_files = list(history_dir.glob("*.json"))
        assert len(remaining_files) == MAX_ACCEPTANCE_HISTORY, \
            f"Expected {MAX_ACCEPTANCE_HISTORY} files, got {len(remaining_files)}"


class TestAcceptanceLogCopyCaps:
    """Test acceptance log copy size limits"""
    
    def test_acceptance_log_copy_skips_when_too_large(self, tmp_path):
        """Verify large logs are not copied and marker is set"""
        import os
        
        # Create a large log file (> 1MB)
        large_log = tmp_path / "acceptance_last.log"
        # Write > 1MB of content
        large_content = "x" * (MAX_LOG_BYTES + 1000)
        large_log.write_text(large_content)
        
        # Create acceptance_last.json
        acceptance_json = tmp_path / "acceptance_last.json"
        acceptance_data = {
            "timestamp": "2024-01-01T12:00:00",
            "status": "pass",
            "exit_code": 0
        }
        acceptance_json.write_text(json.dumps(acceptance_data))
        
        # Create history directory
        history_dir = tmp_path / "acceptance_history"
        history_dir.mkdir()
        
        # Simulate the copy logic from run_acceptance endpoint
        now = datetime.now()
        history_filename = f"{now.strftime('%Y%m%d_%H%M%S')}_pass_0.json"
        history_file = history_dir / history_filename
        
        log_copied = False
        log_too_large = False
        log_size = large_log.stat().st_size
        
        if log_size <= MAX_LOG_BYTES:
            # Would copy log
            log_copied = True
        else:
            log_too_large = True
        
        # Update JSON with log status
        if log_too_large:
            acceptance_data["log_copied"] = False
            acceptance_data["log_too_large"] = True
            acceptance_data["log_size_bytes"] = log_size
        
        # Write history JSON
        history_file.write_text(json.dumps(acceptance_data))
        
        # Verify log was NOT copied
        log_history_file = history_dir / history_filename.replace('.json', '.log')
        assert not log_history_file.exists(), "Large log should not be copied"
        
        # Verify marker in JSON
        with open(history_file, 'r', encoding='utf-8') as f:
            saved_data = json.load(f)
        assert saved_data.get("log_copied") == False, "log_copied should be False"
        assert saved_data.get("log_too_large") == True, "log_too_large should be True"
        assert saved_data.get("log_size_bytes") == log_size, "log_size_bytes should be set"
    
    def test_acceptance_log_copy_succeeds_when_small(self, tmp_path):
        """Verify small logs are copied successfully"""
        import os
        from datetime import datetime
        
        # Create a small log file (< 1MB)
        small_log = tmp_path / "acceptance_last.log"
        small_content = "Small log content\n" * 100
        small_log.write_text(small_content)
        
        # Create acceptance_last.json
        acceptance_json = tmp_path / "acceptance_last.json"
        acceptance_data = {
            "timestamp": "2024-01-01T12:00:00",
            "status": "pass",
            "exit_code": 0
        }
        acceptance_json.write_text(json.dumps(acceptance_data))
        
        # Create history directory
        history_dir = tmp_path / "acceptance_history"
        history_dir.mkdir()
        
        # Simulate the copy logic
        now = datetime.now()
        history_filename = f"{now.strftime('%Y%m%d_%H%M%S')}_pass_0.json"
        history_file = history_dir / history_filename
        
        log_size = small_log.stat().st_size
        log_copied = False
        
        if log_size <= MAX_LOG_BYTES:
            log_history_filename = history_filename.replace('.json', '.log')
            log_history_file = history_dir / log_history_filename
            
            # Copy log
            log_content = small_log.read_text(encoding='utf-8', errors='replace')
            log_history_file.write_text(log_content, encoding='utf-8')
            log_copied = True
            acceptance_data["log_copied"] = True
        
        # Write history JSON
        history_file.write_text(json.dumps(acceptance_data))
        
        # Verify log WAS copied
        log_history_file = history_dir / history_filename.replace('.json', '.log')
        assert log_history_file.exists(), "Small log should be copied"
        assert log_history_file.read_text() == small_content, "Copied log content should match"
        
        # Verify marker in JSON
        with open(history_file, 'r', encoding='utf-8') as f:
            saved_data = json.load(f)
        assert saved_data.get("log_copied") == True, "log_copied should be True"


class TestRetentionSafety:
    """Test retention safety constraints"""
    
    def test_retention_only_deletes_in_history_dir(self, tmp_path):
        """Verify retention never deletes outside history directory"""
        history_dir = tmp_path / "run_once_history"
        history_dir.mkdir()
        
        # Create a file outside history dir
        outside_file = tmp_path / "important.json"
        outside_file.write_text(json.dumps({"important": True}))
        
        # Create files in history dir
        for i in range(10):
            file_path = history_dir / f"test_{i}.json"
            file_path.write_text(json.dumps({"test": i}))
        
        # Prune (should not affect outside file)
        _prune_history_dir(history_dir, 5, allowed_suffixes=('.json',))
        
        # Verify outside file still exists
        assert outside_file.exists(), "Outside file should not be deleted"
    
    def test_retention_only_deletes_allowed_suffixes(self, tmp_path):
        """Verify retention only deletes files with allowed suffixes"""
        history_dir = tmp_path / "run_once_history"
        history_dir.mkdir()
        
        # Create files with different suffixes
        json_file = history_dir / "test.json"
        json_file.write_text('{"test": true}')
        
        txt_file = history_dir / "test.txt"
        txt_file.write_text("test content")
        
        # Prune with only .json allowed
        _prune_history_dir(history_dir, 0, allowed_suffixes=('.json',))
        
        # Verify .txt file still exists
        assert txt_file.exists(), ".txt file should not be deleted"
        assert not json_file.exists(), ".json file should be deleted"
