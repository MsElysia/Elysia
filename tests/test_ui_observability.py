"""
UI Observability Tests
======================
Minimal tests for control panel observability endpoints (history, mutations, diff).
"""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

try:
    from fastapi.testclient import TestClient
    from project_guardian.ui.app import app
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    pytestmark = pytest.mark.skip("FastAPI not available")


@pytest.fixture
def temp_project(tmp_path):
    """Create a temporary project structure"""
    # Create directories
    (tmp_path / "REPORTS").mkdir()
    (tmp_path / "REPORTS" / "run_once_history").mkdir()
    (tmp_path / "REPORTS" / "acceptance_history").mkdir()
    (tmp_path / "MUTATIONS").mkdir()
    (tmp_path / "TASKS").mkdir()
    (tmp_path / "scripts").mkdir()
    
    # Create CONTROL.md
    control_file = tmp_path / "CONTROL.md"
    control_file.write_text("CURRENT_TASK: NONE\n")
    
    return tmp_path


@pytest.fixture
def client(temp_project):
    """Create test client with monkeypatched project root"""
    with patch('project_guardian.ui.app.project_root', temp_project):
        with patch('project_guardian.ui.app.review_queue') as mock_queue:
            mock_queue.list_pending.return_value = []
            with patch('project_guardian.ui.app.approval_store') as mock_store:
                yield TestClient(app)


class TestHistory:
    """Test history endpoints"""
    
    def test_history_list_returns_200(self, client, temp_project):
        """Verify history list loads successfully"""
        # Create some history files
        run_once_history_dir = temp_project / "REPORTS" / "run_once_history"
        history_file = run_once_history_dir / "20240101_120000_idle_none.json"
        history_file.write_text(json.dumps({
            "timestamp": "2024-01-01T12:00:00",
            "result": {"status": "idle", "current_task": None}
        }))
        
        response = client.get("/history")
        assert response.status_code == 200
        assert "Execution History" in response.text
        assert "20240101_120000_idle_none.json" in response.text


class TestMutations:
    """Test mutation endpoints"""
    
    def test_mutations_list_returns_200(self, client, temp_project):
        """Verify mutations list loads successfully"""
        # Create a mutation file
        mutations_dir = temp_project / "MUTATIONS"
        mutation_file = mutations_dir / "test.json"
        mutation_file.write_text(json.dumps({
            "touched_paths": ["test.py"],
            "changes": [{"path": "test.py", "content": "print('test')\n"}],
            "summary": "Test mutation"
        }))
        
        response = client.get("/mutations")
        assert response.status_code == 200
        assert "Mutation Payloads" in response.text
        assert "test.json" in response.text
    
    def test_mutation_detail_returns_200(self, client, temp_project):
        """Verify mutation detail loads successfully"""
        # Create a mutation file
        mutations_dir = temp_project / "MUTATIONS"
        mutation_file = mutations_dir / "test.json"
        mutation_file.write_text(json.dumps({
            "touched_paths": ["test.py"],
            "changes": [{"path": "test.py", "content": "print('test')\n"}],
            "summary": "Test mutation"
        }))
        
        response = client.get("/mutations/test.json")
        assert response.status_code == 200
        assert "test.json" in response.text
        assert "Test mutation" in response.text


class TestDiffViewer:
    """Test diff viewer endpoint"""
    
    def test_diff_rejects_invalid_mutation(self, client):
        """Verify invalid mutation filename returns 400"""
        response = client.get("/diff?mutation=../../../etc/passwd&path=test.py")
        assert response.status_code == 400
        assert "Invalid mutation filename" in response.json()["detail"]
    
    def test_diff_rejects_path_not_in_touched_paths(self, client, temp_project):
        """Verify path not in touched_paths returns 400"""
        # Create a mutation file
        mutations_dir = temp_project / "MUTATIONS"
        mutation_file = mutations_dir / "test.json"
        mutation_file.write_text(json.dumps({
            "touched_paths": ["test.py"],
            "changes": [{"path": "test.py", "content": "print('test')\n"}],
            "summary": "Test mutation"
        }))
        
        response = client.get("/diff?mutation=test.json&path=other.py")
        assert response.status_code == 400
        assert "Path not in mutation touched_paths" in response.json()["detail"]
    
    def test_diff_works_for_valid_payload(self, client, temp_project):
        """Verify diff works for valid payload + path"""
        # Create a mutation file
        mutations_dir = temp_project / "MUTATIONS"
        mutation_file = mutations_dir / "test.json"
        mutation_file.write_text(json.dumps({
            "touched_paths": ["test.py"],
            "changes": [{"path": "test.py", "content": "print('new')\n"}],
            "summary": "Test mutation"
        }))
        
        # Create current file
        test_file = temp_project / "test.py"
        test_file.write_text("print('old')\n")
        
        response = client.get("/diff?mutation=test.json&path=test.py")
        assert response.status_code == 200
        assert "Diff Viewer" in response.text
        assert "test.json" in response.text
        assert "test.py" in response.text
