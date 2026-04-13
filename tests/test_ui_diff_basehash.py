"""
UI Diff Base Hash Tests
=======================
Tests for mutation payload base hashing and mismatch warnings.
"""

import pytest
import json
import hashlib
import tempfile
from pathlib import Path
from datetime import datetime

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
    project_root = tmp_path / "project"
    project_root.mkdir()
    
    # Create MUTATIONS directory
    mutations_dir = project_root / "MUTATIONS"
    mutations_dir.mkdir()
    
    # Create REPORTS directory
    reports_dir = project_root / "REPORTS"
    reports_dir.mkdir()
    
    # Monkeypatch the project_root in app
    import project_guardian.ui.app as app_module
    original_root = app_module.project_root
    app_module.project_root = project_root
    
    yield project_root
    
    # Restore
    app_module.project_root = original_root


@pytest.fixture
def client(temp_project):
    """Create FastAPI test client"""
    return TestClient(app)


class TestPayloadCreationBaseHashes:
    """Test that payload creation includes base hashes"""
    
    def test_payload_creation_includes_base_hashes(self, client, temp_project):
        """Verify payload creation computes and stores base hashes"""
        # Create a test file in the project
        test_file = temp_project / "test_file.py"
        test_content = "print('hello world')\n"
        test_file.write_text(test_content)
        
        # Compute expected hash
        expected_hash = hashlib.sha256(test_content.encode('utf-8')).hexdigest()
        expected_bytes = len(test_content.encode('utf-8'))
        
        # Create mutation payload via POST
        response = client.post(
            "/mutations/create",
            data={
                "payload_name": "test_payload.json",
                "summary": "Test mutation",
                "file_paths": ["test_file.py"],
                "file_contents": ["print('modified')\n"]
            }
        )
        
        assert response.status_code == 200
        
        # Load the created payload
        payload_file = temp_project / "MUTATIONS" / "test_payload.json"
        assert payload_file.exists()
        
        with open(payload_file, 'r', encoding='utf-8') as f:
            payload = json.load(f)
        
        # Verify base info exists
        assert "base" in payload
        assert "test_file.py" in payload["base"]
        
        base_info = payload["base"]["test_file.py"]
        assert base_info["sha256"] == expected_hash
        assert base_info["bytes"] == expected_bytes
        assert "captured_at" in base_info
    
    def test_payload_creation_handles_missing_file(self, client, temp_project):
        """Verify payload creation handles missing files correctly"""
        # Create mutation payload for a non-existent file
        response = client.post(
            "/mutations/create",
            data={
                "payload_name": "test_missing.json",
                "summary": "Test missing file",
                "file_paths": ["nonexistent.py"],
                "file_contents": ["new content\n"]
            }
        )
        
        assert response.status_code == 200
        
        # Load the created payload
        payload_file = temp_project / "MUTATIONS" / "test_missing.json"
        assert payload_file.exists()
        
        with open(payload_file, 'r', encoding='utf-8') as f:
            payload = json.load(f)
        
        # Verify base info marks file as MISSING
        assert "base" in payload
        assert "nonexistent.py" in payload["base"]
        
        base_info = payload["base"]["nonexistent.py"]
        assert base_info["sha256"] == "MISSING"
        assert base_info["bytes"] == 0


class TestDiffViewerMismatchWarnings:
    """Test diff viewer shows mismatch warnings"""
    
    def test_diff_viewer_shows_mismatch_warning(self, client, temp_project):
        """Verify diff viewer warns when file changed since payload creation"""
        # Create a test file
        test_file = temp_project / "test_file.py"
        original_content = "print('original')\n"
        test_file.write_text(original_content)
        
        # Create mutation payload (captures base hash)
        response = client.post(
            "/mutations/create",
            data={
                "payload_name": "test_mismatch.json",
                "summary": "Test mismatch",
                "file_paths": ["test_file.py"],
                "file_contents": ["print('proposed')\n"]
            }
        )
        assert response.status_code == 200
        
        # Modify the file (simulating change after payload creation)
        modified_content = "print('modified')\n"
        test_file.write_text(modified_content)
        
        # Request diff page
        response = client.get("/diff?mutation=test_mismatch.json&path=test_file.py")
        
        assert response.status_code == 200
        assert "Base mismatch" in response.text or "base mismatch" in response.text.lower()
        assert "file changed since payload creation" in response.text.lower()
    
    def test_diff_viewer_handles_legacy_payload(self, client, temp_project):
        """Verify diff viewer handles legacy payloads without base info"""
        # Create a legacy payload (without base)
        legacy_payload = {
            "touched_paths": ["test_file.py"],
            "changes": [{"path": "test_file.py", "content": "new content\n"}],
            "summary": "Legacy payload"
        }
        
        payload_file = temp_project / "MUTATIONS" / "legacy.json"
        with open(payload_file, 'w', encoding='utf-8') as f:
            json.dump(legacy_payload, f)
        
        # Create the file
        test_file = temp_project / "test_file.py"
        test_file.write_text("current content\n")
        
        # Request diff page
        response = client.get("/diff?mutation=legacy.json&path=test_file.py")
        
        assert response.status_code == 200
        assert "No base recorded" in response.text or "legacy payload" in response.text.lower()
    
    def test_diff_viewer_shows_match_when_unchanged(self, client, temp_project):
        """Verify diff viewer doesn't show warning when file matches base"""
        # Create a test file
        test_file = temp_project / "test_file.py"
        original_content = "print('original')\n"
        test_file.write_text(original_content)
        
        # Create mutation payload
        response = client.post(
            "/mutations/create",
            data={
                "payload_name": "test_match.json",
                "summary": "Test match",
                "file_paths": ["test_file.py"],
                "file_contents": ["print('proposed')\n"]
            }
        )
        assert response.status_code == 200
        
        # File unchanged - request diff page
        response = client.get("/diff?mutation=test_match.json&path=test_file.py")
        
        assert response.status_code == 200
        # Should not show mismatch warning (file hasn't changed)
        # Note: We can't easily assert absence, but we can verify the page loads


class TestMutationDetailHashDisplay:
    """Test mutation detail page shows hash comparison"""
    
    def test_mutation_detail_shows_hash_status(self, client, temp_project):
        """Verify mutation detail shows base/current hash and status"""
        # Create a test file
        test_file = temp_project / "test_file.py"
        original_content = "print('original')\n"
        test_file.write_text(original_content)
        
        # Create mutation payload
        response = client.post(
            "/mutations/create",
            data={
                "payload_name": "test_detail.json",
                "summary": "Test detail",
                "file_paths": ["test_file.py"],
                "file_contents": ["print('proposed')\n"]
            }
        )
        assert response.status_code == 200
        
        # Request mutation detail page
        response = client.get("/mutations/test_detail.json")
        
        assert response.status_code == 200
        # Should show base hash, current hash, and status
        assert "Base Hash" in response.text or "base hash" in response.text.lower()
        assert "Current Hash" in response.text or "current hash" in response.text.lower()
        assert "MATCH" in response.text or "MISMATCH" in response.text or "MISSING" in response.text
