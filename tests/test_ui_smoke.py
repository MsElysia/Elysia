"""
UI Smoke Tests
==============
Minimal tests for control panel UI endpoints.
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
    (tmp_path / "TASKS").mkdir()
    (tmp_path / "MUTATIONS").mkdir()
    (tmp_path / "scripts").mkdir()
    
    # Create CONTROL.md
    control_file = tmp_path / "CONTROL.md"
    control_file.write_text("CURRENT_TASK: NONE\n")
    
    # Create acceptance script
    acceptance_script = tmp_path / "scripts" / "acceptance.ps1"
    acceptance_script.write_text("# Mock acceptance script\n")
    
    return tmp_path


@pytest.fixture
def client(temp_project):
    """Create test client with monkeypatched project root"""
    with patch('project_guardian.ui.app.project_root', temp_project):
        with patch('project_guardian.ui.app.review_queue') as mock_queue:
            mock_queue.list_pending.return_value = []
            with patch('project_guardian.ui.app.approval_store') as mock_store:
                yield TestClient(app)


class TestDashboard:
    """Test dashboard endpoint"""
    
    def test_dashboard_returns_200(self, client):
        """Verify dashboard loads successfully"""
        response = client.get("/")
        assert response.status_code == 200
        assert "Project Guardian Control Panel" in response.text
        assert "Current Task" in response.text


class TestRunOnce:
    """Test run_once endpoint"""
    
    def test_run_once_creates_artifact(self, client, temp_project):
        """Verify run_once creates artifact and redirects"""
        with patch('project_guardian.ui.app.GuardianCore') as mock_core_class:
            mock_core = MagicMock()
            mock_core.run_once.return_value = {
                "status": "idle",
                "current_task": None
            }
            mock_core_class.return_value = mock_core
            
            response = client.post("/control/run-once", follow_redirects=False)
            
            # Should redirect
            assert response.status_code == 302
            
            # Artifact should be created
            artifact_file = temp_project / "REPORTS" / "run_once_last.json"
            assert artifact_file.exists()
            
            # Verify artifact content
            with open(artifact_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                assert "timestamp" in data
                assert "result" in data
                assert data["result"]["status"] == "idle"


class TestTaskCreation:
    """Test task creation endpoint"""
    
    def test_create_task_invalid_id(self, client):
        """Verify invalid task_id returns 400"""
        response = client.post("/tasks/create", data={
            "task_id": "INVALID",
            "task_type": "RUN_ACCEPTANCE"
        })
        assert response.status_code == 400
        assert "Invalid task_id format" in response.json()["detail"]
    
    def test_create_task_valid(self, client, temp_project):
        """Verify valid task creation"""
        response = client.post("/tasks/create", data={
            "task_id": "TASK-0001",
            "task_type": "RUN_ACCEPTANCE",
            "activate_now": "false"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "created"
        assert data["task_id"] == "TASK-0001"
        
        # Verify task file created
        task_file = temp_project / "TASKS" / "TASK-0001.md"
        assert task_file.exists()
        content = task_file.read_text()
        assert "TASK_TYPE: RUN_ACCEPTANCE" in content
    
    def test_create_task_apply_mutation(self, client, temp_project):
        """Verify APPLY_MUTATION task creation with mutation file"""
        # Create mutation file first
        mutation_file = temp_project / "MUTATIONS" / "test.json"
        mutation_file.write_text(json.dumps({
            "touched_paths": ["test.py"],
            "changes": [{"path": "test.py", "content": "print('test')\n"}],
            "summary": "Test mutation"
        }))
        
        response = client.post("/tasks/create", data={
            "task_id": "TASK-0002",
            "task_type": "APPLY_MUTATION",
            "mutation_file": "MUTATIONS/test.json",
            "allow_governance_mutation": "false",
            "activate_now": "false"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "created"
        
        # Verify task file
        task_file = temp_project / "TASKS" / "TASK-0002.md"
        assert task_file.exists()
        content = task_file.read_text()
        assert "TASK_TYPE: APPLY_MUTATION" in content
        assert "MUTATION_FILE: MUTATIONS/test.json" in content


class TestMutationCreation:
    """Test mutation payload creation endpoint"""
    
    def test_create_mutation_invalid_path(self, client):
        """Verify invalid path (with ..) returns 400"""
        response = client.post("/mutations/create", data={
            "payload_name": "test.json",
            "summary": "Test mutation",
            "file_paths": ["../../../etc/passwd"],
            "file_contents": ["malicious content"]
        })
        assert response.status_code == 400
        assert "Invalid path" in response.json()["detail"]
    
    def test_create_mutation_valid(self, client, temp_project):
        """Verify valid mutation payload creation"""
        response = client.post("/mutations/create", data={
            "payload_name": "test.json",
            "summary": "Test mutation",
            "file_paths": ["test.py"],
            "file_contents": ["print('test')\n"]
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "created"
        
        # Verify mutation file created
        mutation_file = temp_project / "MUTATIONS" / "test.json"
        assert mutation_file.exists()
        
        with open(mutation_file, 'r', encoding='utf-8') as f:
            payload = json.load(f)
            assert "touched_paths" in payload
            assert "changes" in payload
            assert "summary" in payload
            assert payload["touched_paths"] == ["test.py"]
            assert len(payload["changes"]) == 1
    
    def test_create_mutation_path_mismatch(self, client):
        """Verify path mismatch returns 400"""
        response = client.post("/mutations/create", data={
            "payload_name": "test.json",
            "summary": "Test mutation",
            "file_paths": ["test.py", "other.py"],
            "file_contents": ["print('test')\n"]
        })
        assert response.status_code == 400
        assert "touched_paths must match" in response.json()["detail"]
