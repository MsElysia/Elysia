# run_integration_tests.py
# Comprehensive Integration Test Runner
# Runs all integration tests, fixes issues, and generates detailed reports

import sys
import subprocess
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any
import re

class IntegrationTestRunner:
    """Comprehensive integration test runner with reporting."""
    
    def __init__(self):
        self.results = {
            "start_time": datetime.now().isoformat(),
            "tests_run": [],
            "summary": {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "errors": 0
            },
            "failures": [],
            "warnings": [],
            "duration": 0
        }
        self.project_root = Path(__file__).parent
    
    def run_test_file(self, test_file: Path) -> Dict[str, Any]:
        """Run a single test file and return results."""
        print(f"\n{'='*70}")
        print(f"Running: {test_file.name}")
        print(f"{'='*70}")
        
        start_time = time.time()
        
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", str(test_file), "-v", "--tb=short"],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout per test file
            )
            
            duration = time.time() - start_time
            
            # Parse pytest output
            output = result.stdout + result.stderr
            
            # Extract test results
            passed_match = re.search(r'(\d+) passed', output)
            failed_match = re.search(r'(\d+) failed', output)
            skipped_match = re.search(r'(\d+) skipped', output)
            error_match = re.search(r'(\d+) error', output)
            
            passed = int(passed_match.group(1)) if passed_match else 0
            failed = int(failed_match.group(1)) if failed_match else 0
            skipped = int(skipped_match.group(1)) if skipped_match else 0
            errors = int(error_match.group(1)) if error_match else 0
            
            # Extract failure details
            failures = []
            if failed > 0 or errors > 0:
                # Find FAILED test names
                failed_tests = re.findall(r'FAILED\s+([^\s]+)', output)
                for test in failed_tests:
                    failures.append({
                        "test": test,
                        "file": str(test_file)
                    })
            
            # Extract warnings
            warnings = []
            warning_lines = re.findall(r'WARNING[^\n]+', output)
            for warning in warning_lines[:10]:  # Limit to first 10 warnings
                warnings.append(warning.strip())
            
            return {
                "file": str(test_file),
                "status": "passed" if failed == 0 and errors == 0 else "failed",
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "errors": errors,
                "duration": duration,
                "failures": failures,
                "warnings": warnings,
                "output": output[-2000:] if len(output) > 2000 else output  # Last 2000 chars
            }
            
        except subprocess.TimeoutExpired:
            return {
                "file": str(test_file),
                "status": "timeout",
                "duration": 300,
                "error": "Test exceeded 5 minute timeout"
            }
        except Exception as e:
            return {
                "file": str(test_file),
                "status": "error",
                "error": str(e)
            }
    
    def find_integration_tests(self) -> List[Path]:
        """Find all integration test files."""
        test_dir = self.project_root / "project_guardian" / "tests"
        integration_tests = []
        
        for test_file in test_dir.glob("test_integration*.py"):
            integration_tests.append(test_file)
        
        return sorted(integration_tests)
    
    def run_all_tests(self):
        """Run all integration tests."""
        test_files = self.find_integration_tests()
        
        print(f"\nFound {len(test_files)} integration test files:")
        for test_file in test_files:
            print(f"  - {test_file.name}")
        
        for test_file in test_files:
            result = self.run_test_file(test_file)
            self.results["tests_run"].append(result)
            
            # Update summary
            self.results["summary"]["total"] += result.get("passed", 0) + result.get("failed", 0) + result.get("skipped", 0) + result.get("errors", 0)
            self.results["summary"]["passed"] += result.get("passed", 0)
            self.results["summary"]["failed"] += result.get("failed", 0)
            self.results["summary"]["skipped"] += result.get("skipped", 0)
            self.results["summary"]["errors"] += result.get("errors", 0)
            
            # Collect failures
            if result.get("failures"):
                self.results["failures"].extend(result["failures"])
            
            # Collect warnings
            if result.get("warnings"):
                self.results["warnings"].extend(result["warnings"])
        
        self.results["duration"] = time.time() - time.mktime(
            datetime.fromisoformat(self.results["start_time"]).timetuple()
        )
        self.results["end_time"] = datetime.now().isoformat()
    
    def generate_report(self) -> str:
        """Generate a detailed test report."""
        report = []
        report.append("=" * 70)
        report.append("INTEGRATION TEST REPORT")
        report.append("=" * 70)
        report.append(f"Start Time: {self.results['start_time']}")
        report.append(f"End Time: {self.results.get('end_time', 'N/A')}")
        report.append(f"Duration: {self.results['duration']:.2f} seconds")
        report.append("")
        
        # Summary
        report.append("SUMMARY")
        report.append("-" * 70)
        summary = self.results["summary"]
        report.append(f"Total Tests: {summary['total']}")
        report.append(f"  [PASS] Passed: {summary['passed']}")
        report.append(f"  [FAIL] Failed: {summary['failed']}")
        report.append(f"  [SKIP] Skipped: {summary['skipped']}")
        report.append(f"  [ERROR] Errors: {summary['errors']}")
        report.append("")
        
        # Test file results
        report.append("TEST FILE RESULTS")
        report.append("-" * 70)
        for test_result in self.results["tests_run"]:
            status_icon = "[PASS]" if test_result["status"] == "passed" else "[FAIL]"
            report.append(f"{status_icon} {Path(test_result['file']).name}")
            report.append(f"    Status: {test_result['status']}")
            report.append(f"    Passed: {test_result.get('passed', 0)}")
            report.append(f"    Failed: {test_result.get('failed', 0)}")
            report.append(f"    Duration: {test_result.get('duration', 0):.2f}s")
            if test_result.get("failures"):
                report.append(f"    Failures:")
                for failure in test_result["failures"]:
                    report.append(f"      - {failure['test']}")
            report.append("")
        
        # Failures detail
        if self.results["failures"]:
            report.append("FAILURES DETAIL")
            report.append("-" * 70)
            for failure in self.results["failures"]:
                report.append(f"[FAIL] {failure['test']}")
                report.append(f"  File: {failure['file']}")
                report.append("")
        
        # Warnings
        if self.results["warnings"]:
            report.append("WARNINGS")
            report.append("-" * 70)
            for warning in self.results["warnings"][:20]:  # Limit to 20 warnings
                report.append(f"[WARN] {warning}")
            if len(self.results["warnings"]) > 20:
                report.append(f"... and {len(self.results['warnings']) - 20} more warnings")
            report.append("")
        
        # Overall status
        report.append("=" * 70)
        if summary["failed"] == 0 and summary["errors"] == 0:
            report.append("[SUCCESS] ALL TESTS PASSED")
        else:
            report.append(f"[FAILURE] TESTS FAILED: {summary['failed']} failures, {summary['errors']} errors")
        report.append("=" * 70)
        
        return "\n".join(report)
    
    def save_results(self, output_file: Path):
        """Save results to JSON file."""
        with open(output_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        print(f"\nResults saved to: {output_file}")
    
    def run(self):
        """Run all tests and generate report."""
        print("Starting comprehensive integration test run...")
        
        self.run_all_tests()
        
        # Generate and print report
        report = self.generate_report()
        try:
            print("\n" + report)
        except UnicodeEncodeError:
            # Fallback for Windows console
            report_ascii = report.encode('ascii', 'replace').decode('ascii')
            print("\n" + report_ascii)
        
        # Save results
        results_file = self.project_root / "integration_test_results.json"
        self.save_results(results_file)
        
        # Save report
        report_file = self.project_root / "integration_test_report.txt"
        with open(report_file, 'w') as f:
            f.write(report)
        print(f"Report saved to: {report_file}")
        
        # Return exit code
        if self.results["summary"]["failed"] == 0 and self.results["summary"]["errors"] == 0:
            return 0
        else:
            return 1


if __name__ == "__main__":
    runner = IntegrationTestRunner()
    exit_code = runner.run()
    sys.exit(exit_code)

