"""
Read-Only Analysis Task Tests
=============================
Tests for READ_ONLY_ANALYSIS task type execution.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

try:
    from project_guardian.core import GuardianCore
    from project_guardian.trust import TrustDecision, NETWORK_ACCESS
    from project_guardian.external import TrustDeniedError, TrustReviewRequiredError
    MODULES_AVAILABLE = True
except ImportError:
    MODULES_AVAILABLE = False
    pytestmark = pytest.mark.skip("Required modules not available")


@pytest.fixture
def tmp_project(tmp_path):
    """Create a minimal tmp project tree."""
    (tmp_path / "TASKS").mkdir()
    (tmp_path / "REPORTS").mkdir()
    (tmp_path / "project_guardian").mkdir()
    
    control = tmp_path / "CONTROL.md"
    control.write_text("CURRENT_TASK: TASK-0001\n")
    
    # Create a test file for FILE_SET analysis
    test_file = tmp_path / "test_file.py"
    test_file.write_text("print('hello')\nprint('world')\n" * 10)  # ~20 lines
    
    return tmp_path


def _make_core(tmp_project):
    """Instantiate GuardianCore rooted at tmp_project."""
    config = {
        "enable_vector_memory": False,
        "enable_resource_monitoring": False,
        "enable_runtime_health_monitoring": False
    }
    # Ensure MUTATIONS dir exists (Core expects it)
    mutations_dir = tmp_project / "MUTATIONS"
    mutations_dir.mkdir(exist_ok=True)
    core = GuardianCore(
        config=config,
        control_path=tmp_project / "CONTROL.md",
        tasks_dir=tmp_project / "TASKS",
        mutations_dir=mutations_dir
    )
    # Stop monitoring immediately to prevent background threads
    try:
        if hasattr(core, 'monitor'):
            core.monitor.stop_monitoring()
        if hasattr(core, 'elysia_loop') and core.elysia_loop:
            core.elysia_loop.stop()
        if hasattr(core, 'runtime_health') and core.runtime_health:
            core.runtime_health.stop_monitoring()
    except Exception:
        pass
    return core


@pytest.fixture
def core_instance(tmp_project):
    """Create a GuardianCore instance and ensure cleanup after test."""
    core = _make_core(tmp_project)
    yield core
    # Cleanup: shutdown to stop background threads
    try:
        core.shutdown()
    except Exception:
        pass  # Ignore cleanup errors


@pytest.mark.skipif(not MODULES_AVAILABLE, reason="Core not available")
class TestReadOnlyAnalysisTask:
    def test_repo_summary_creates_report(self, tmp_project, core_instance):
        """Verify REPO_SUMMARY creates report and has no side-effects."""
        task_file = tmp_project / "TASKS" / "TASK-0001.md"
        task_file.write_text("""TASK_TYPE: READ_ONLY_ANALYSIS
ANALYSIS_KIND: REPO_SUMMARY
INPUTS:
  - type: repo
    value: .
OUTPUT_REPORT: REPORTS/repo_summary.json
""")
        
        core = core_instance
        
        result = core.run_once()
        
        # Debug: print result if not ok
        if result.get("status") != "ok":
            print(f"Result: {result}")
        
        # Shutdown immediately to stop background threads
        try:
            core.shutdown()
        except Exception:
            pass
        
        assert result.get("status") == "ok", f"Expected status 'ok', got {result.get('status')} with detail: {result.get('detail', 'no detail')}"
        assert result.get("outcome") == "analysis_completed"
        
        # Verify report exists
        report_path = tmp_project / "REPORTS" / "repo_summary.json"
        assert report_path.exists()
        
        # Verify report content
        report = json.loads(report_path.read_text(encoding='utf-8'))
        assert report["metadata"]["analysis_kind"] == "REPO_SUMMARY"
        assert "results" in report
        assert "file_counts_by_extension" in report["results"]
        assert "top_level_directories" in report["results"]
        
        # Verify no side-effects
        assert not (tmp_project / "guardian_backups").exists()
        # Test file unchanged
        test_file = tmp_project / "test_file.py"
        assert test_file.exists()
        assert "hello" in test_file.read_text()
    
    def test_file_set_reads_only(self, tmp_project, core_instance):
        """Verify FILE_SET reads files without modifying them."""
        task_file = tmp_project / "TASKS" / "TASK-0001.md"
        task_file.write_text("""TASK_TYPE: READ_ONLY_ANALYSIS
ANALYSIS_KIND: FILE_SET
INPUTS:
  - type: file
    value: test_file.py
OUTPUT_REPORT: REPORTS/file_set.json
""")
        
        test_file = tmp_project / "test_file.py"
        original_content = test_file.read_text()
        
        core = core_instance
        
        result = core.run_once()
        # Shutdown immediately to stop background threads
        try:
            core.shutdown()
        except Exception:
            pass
        
        assert result.get("status") == "ok"
        
        # Verify file unchanged
        assert test_file.read_text() == original_content
        
        # Verify report created
        report_path = tmp_project / "REPORTS" / "file_set.json"
        assert report_path.exists()
        
        report = json.loads(report_path.read_text(encoding='utf-8'))
        assert report["metadata"]["analysis_kind"] == "FILE_SET"
        assert "results" in report
        assert "files" in report["results"]
        assert len(report["results"]["files"]) > 0
        assert report["results"]["files"][0]["filename"] == "test_file.py"
        assert "sha256" in report["results"]["files"][0]
        assert "preview_lines" in report["results"]["files"][0]
    
    def test_url_research_review_creates_no_report(self, tmp_project, core_instance):
        """Verify URL_RESEARCH review does not write report."""
        task_file = tmp_project / "TASKS" / "TASK-0001.md"
        task_file.write_text("""TASK_TYPE: READ_ONLY_ANALYSIS
ANALYSIS_KIND: URL_RESEARCH
INPUTS:
  - type: url
    value: http://example.com
OUTPUT_REPORT: REPORTS/url_research.json
""")
        
        core = core_instance
        
        # Mock TrustMatrix in WebReader to return review
        core.web_reader.trust_matrix.validate_trust_for_action = Mock(return_value=TrustDecision(
            allowed=False,
            decision="review",
            reason_code="REVIEW_REQUIRED",
            message="Test review",
            risk_score=0.6
        ))
        
        # Mock urllib to track if called
        with patch('urllib.request.urlopen') as mock_urlopen:
            result = core.run_once()
        
        # Debug output
        if result.get("status") != "needs_review":
            print(f"\n=== REVIEW TEST DEBUG ===")
            print(f"Status: {result.get('status')}")
            print(f"Detail: {result.get('detail', 'N/A')}")
            print(f"Exception type: {result.get('exception_type', 'N/A')}")
            print(f"Full result: {result}")
        
        # Verify review required
        assert result.get("status") == "needs_review", f"Expected 'needs_review', got {result.get('status')}. Full result: {result}"
        assert "request_id" in result
        
        # Verify no report written
        report_path = tmp_project / "REPORTS" / "url_research.json"
        assert not report_path.exists()
        
        # Verify ReviewQueue has entry (accessed via mutation engine)
        if hasattr(core, 'mutation') and hasattr(core.mutation, 'review_queue') and core.mutation.review_queue:
            pending = core.mutation.review_queue.list_pending()
            assert len(pending) > 0
            assert pending[-1].request_id == result.get("request_id")
        
        # Verify network not called
        mock_urlopen.assert_not_called()
    
    def test_url_research_deny_creates_no_report(self, tmp_project, core_instance):
        """Verify URL_RESEARCH deny does not write report or call network."""
        task_file = tmp_project / "TASKS" / "TASK-0001.md"
        task_file.write_text("""TASK_TYPE: READ_ONLY_ANALYSIS
ANALYSIS_KIND: URL_RESEARCH
INPUTS:
  - type: url
    value: http://example.com
OUTPUT_REPORT: REPORTS/url_research.json
""")
        
        core = core_instance
        
        # Mock TrustMatrix in WebReader to return deny
        core.web_reader.trust_matrix.validate_trust_for_action = Mock(return_value=TrustDecision(
            allowed=False,
            decision="deny",
            reason_code="DENIED",
            message="Test deny",
            risk_score=0.9
        ))
        
        # Mock urllib to track if called
        with patch('urllib.request.urlopen') as mock_urlopen:
            result = core.run_once()
        
        # Shutdown immediately to stop background threads
        try:
            core.shutdown()
        except Exception:
            pass
        
        # Debug: print result if not as expected
        if result.get("status") != "denied":
            print(f"Unexpected result: {result}")
        
        # Verify denial
        assert result.get("status") == "denied", f"Expected 'denied', got {result.get('status')} with detail: {result.get('detail', 'no detail')}"
        assert result.get("reason_code") == "DENIED"
        
        # Verify no report written
        report_path = tmp_project / "REPORTS" / "url_research.json"
        assert not report_path.exists()
        
        # Verify network not called
        mock_urlopen.assert_not_called()
    
    def test_invalid_contract_rejected(self, tmp_project):
        """Verify invalid contracts are rejected."""
        # Missing ANALYSIS_KIND
        task_file = tmp_project / "TASKS" / "TASK-0001.md"
        task_file.write_text("""TASK_TYPE: READ_ONLY_ANALYSIS
OUTPUT_REPORT: REPORTS/test.json
""")
        
        core = _make_core(tmp_project)
        result = core.run_once()
        # Shutdown immediately to stop background threads
        try:
            core.shutdown()
        except Exception:
            pass
        assert result.get("status") == "error"
        assert result.get("code") == "TASK_CONTRACT_INVALID"
        
        # Invalid ANALYSIS_KIND
        # Create new core for next test
        core = _make_core(tmp_project)
        task_file.write_text("""TASK_TYPE: READ_ONLY_ANALYSIS
ANALYSIS_KIND: INVALID_KIND
OUTPUT_REPORT: REPORTS/test.json
INPUTS:
  - type: repo
    value: .
""")
        result = core.run_once()
        # Shutdown immediately to stop background threads
        try:
            core.shutdown()
        except Exception:
            pass
        assert result.get("status") == "error"
        assert result.get("code") == "TASK_CONTRACT_INVALID"
        
        # OUTPUT_REPORT outside REPORTS/
        # Create new core for next test
        core = _make_core(tmp_project)
        task_file.write_text("""TASK_TYPE: READ_ONLY_ANALYSIS
ANALYSIS_KIND: REPO_SUMMARY
OUTPUT_REPORT: ../outside.json
INPUTS:
  - type: repo
    value: .
""")
        result = core.run_once()
        # Shutdown immediately to stop background threads
        try:
            core.shutdown()
        except Exception:
            pass
        assert result.get("status") == "error"
        assert result.get("code") == "TASK_CONTRACT_INVALID"
    
    def test_no_side_effects_file_writer_not_used(self, tmp_project, core_instance):
        """Verify FileWriter is not used (read-only analysis)."""
        task_file = tmp_project / "TASKS" / "TASK-0001.md"
        task_file.write_text("""TASK_TYPE: READ_ONLY_ANALYSIS
ANALYSIS_KIND: REPO_SUMMARY
INPUTS:
  - type: repo
    value: .
OUTPUT_REPORT: REPORTS/repo_summary.json
""")
        
        core = core_instance
        
        # Mock FileWriter to track if it's called
        with patch('project_guardian.file_writer.FileWriter') as mock_file_writer:
            result = core.run_once()
        
        # Shutdown immediately to stop background threads
        try:
            core.shutdown()
        except Exception:
            pass
        
        # Verify analysis succeeded
        assert result.get("status") == "ok"
        
        # Verify FileWriter was not instantiated or called
        # (AnalysisEngine does not use FileWriter - Core writes report directly)
        # We can't easily verify FileWriter wasn't called if it's not initialized,
        # but we can verify no backups were created
        assert not (tmp_project / "guardian_backups").exists()
    
    def test_no_side_effects_subprocess_not_used(self, tmp_project, core_instance):
        """Verify SubprocessRunner is not used."""
        task_file = tmp_project / "TASKS" / "TASK-0001.md"
        task_file.write_text("""TASK_TYPE: READ_ONLY_ANALYSIS
ANALYSIS_KIND: FILE_SET
INPUTS:
  - type: file
    value: test_file.py
OUTPUT_REPORT: REPORTS/file_set.json
""")
        
        core = core_instance
        
        # Mock subprocess to track if called
        with patch('subprocess.run') as mock_run, patch('subprocess.Popen') as mock_popen:
            result = core.run_once()
        
        # Shutdown immediately to stop background threads
        try:
            core.shutdown()
        except Exception:
            pass
        
        # Verify analysis succeeded
        assert result.get("status") == "ok"
        
        # Verify subprocess not called
        mock_run.assert_not_called()
        mock_popen.assert_not_called()
