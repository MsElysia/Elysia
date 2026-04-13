"""
Module Matrix Tests
===================
Tests for module completeness matrix generator.
"""

import pytest
import json
import tempfile
from pathlib import Path

try:
    from scripts.module_matrix import (
        analyze_modules,
        generate_json_report,
        generate_markdown_report,
        get_module_shortname,
        check_spec_exists,
        check_audit_exists,
        is_loopback,
    )
    MODULE_MATRIX_AVAILABLE = True
except ImportError:
    MODULE_MATRIX_AVAILABLE = False
    pytestmark = pytest.mark.skip("module_matrix script not available")


class TestModuleMatrix:
    """Test module matrix generation"""
    
    def test_get_module_shortname(self):
        """Test module shortname extraction"""
        from scripts.module_matrix import PROJECT_ROOT
        
        # Test simple module
        module_path = PROJECT_ROOT / "project_guardian" / "trust.py"
        assert get_module_shortname(module_path) == "trust"
        
        # Test UI module
        module_path = PROJECT_ROOT / "project_guardian" / "ui" / "app.py"
        assert get_module_shortname(module_path) == "ui"
    
    def test_check_spec_exists(self):
        """Test spec existence check"""
        # Trust should have a spec
        assert check_spec_exists("trust") == True
        
        # Non-existent module should not
        assert check_spec_exists("nonexistent_module_xyz") == False
    
    def test_check_audit_exists(self):
        """Test audit existence check"""
        # Trust should have an audit
        assert check_audit_exists("trust") == True
        
        # Non-existent module should not
        assert check_audit_exists("nonexistent_module_xyz") == False
    
    def test_analyze_modules_produces_records(self):
        """Test that analyze_modules produces records"""
        records = analyze_modules()
        
        assert len(records) > 0
        
        # Check that known modules are present
        module_names = [r["module"] for r in records]
        assert any("trust" in m for m in module_names)
        assert any("core" in m for m in module_names)
        assert any("ui" in m for m in module_names)
        
        # Check record structure
        for record in records:
            assert "module" in record
            assert "path" in record
            assert "spec_exists" in record
            assert "audit_exists" in record
            assert "tests_exist" in record
            assert "wired_in_core" in record
            assert "bypass_clean" in record
            assert "status" in record
            assert "notes" in record
    
    def test_generate_json_report(self, tmp_path):
        """Test JSON report generation"""
        from scripts.module_matrix import REPORTS_DIR
        
        # Create sample records
        records = [
            {
                "module": "project_guardian.test_module",
                "path": "project_guardian/test_module.py",
                "shortname": "test_module",
                "spec_exists": True,
                "audit_exists": False,
                "tests_exist": True,
                "wired_in_core": False,
                "bypass_clean": True,
                "bypass_issues": [],
                "status": "⚠️ partial",
                "notes": ["Missing audit", "Not wired in core"]
            }
        ]
        
        # Temporarily override REPORTS_DIR
        import scripts.module_matrix as mm
        original_reports_dir = mm.REPORTS_DIR
        mm.REPORTS_DIR = tmp_path
        
        try:
            json_file = generate_json_report(records)
            assert json_file.exists()
            
            # Verify JSON content
            with open(json_file, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            
            assert len(loaded) == 1
            assert loaded[0]["module"] == "project_guardian.test_module"
        finally:
            mm.REPORTS_DIR = original_reports_dir
    
    def test_known_modules_have_correct_status(self):
        """Test that known complete modules are marked correctly"""
        records = analyze_modules()
        
        # Find trust module
        trust_record = next((r for r in records if "trust" in r["module"] and r["shortname"] == "trust"), None)
        if trust_record:
            # Trust should have spec and audit
            assert trust_record["spec_exists"] == True
            assert trust_record["audit_exists"] == True
        
        # Find core module
        core_record = next((r for r in records if "core" in r["module"] and r["shortname"] == "core"), None)
        if core_record:
            # Core should be wired in itself
            assert core_record["wired_in_core"] == True
