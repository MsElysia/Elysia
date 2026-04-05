# Acceptance Runner Script
# Runs basic repo checks (format/lint/tests) based on detected tooling
# Exits 0 if no tooling is configured (non-failing pipeline)

$ErrorActionPreference = "Continue"
$checksRun = @()
$checksSkipped = @()

Write-Host "========================================"
Write-Host "Elysia Acceptance Runner"
Write-Host "========================================"
Write-Host ""

# Detect project root
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

# Ensure REPORTS directory exists
$reportsDir = Join-Path $projectRoot "REPORTS"
if (-not (Test-Path $reportsDir)) {
    New-Item -ItemType Directory -Path $reportsDir -Force | Out-Null
}

# Start time for duration calculation
$startTime = Get-Date

# Check for Python project
$isPythonProject = $false
if (Test-Path "requirements.txt") {
    $isPythonProject = $true
    Write-Host "[DETECTED] Python project (requirements.txt found)"
}

# Check for Node.js project
$isNodeProject = $false
if (Test-Path "package.json") {
    $isNodeProject = $true
    Write-Host "[DETECTED] Node.js project (package.json found)"
    $packageJson = Get-Content "package.json" | ConvertFrom-Json
    
    # Check for npm scripts
    if ($packageJson.scripts) {
        Write-Host "[DETECTED] npm scripts available"
    }
}

Write-Host ""

# Python checks
if ($isPythonProject) {
    Write-Host "--- Python Checks ---"
    
    # Check for pytest
    $pytestExitCode = 0
    $invariantExitCode = 0
    $pytestOutput = ""
    $invariantOutput = ""
    try {
        $pytestCheck = python -m pytest --version 2>&1
        if ($LASTEXITCODE -eq 0 -or $pytestCheck -match "pytest") {
            Write-Host "[RUNNING] pytest tests..."
            $pytestOutput = python -m pytest tests/ -v --tb=short 2>&1 | Out-String
            $pytestExitCode = $LASTEXITCODE
            if ($pytestExitCode -eq 0) {
                $checksRun += "pytest: PASSED"
                Write-Host "[OK] pytest tests passed"
            } else {
                $checksRun += "pytest: FAILED (exit code $pytestExitCode)"
                Write-Host "[FAILED] pytest tests failed (exit code $pytestExitCode)"
            }
            
            # Run invariant tests specifically
            Write-Host "[RUNNING] Invariant tests (SPEC.md governance checks)..."
            $invariantOutput = python -m pytest tests/test_invariants.py -v 2>&1 | Out-String
            $invariantExitCode = $LASTEXITCODE
            if ($invariantExitCode -eq 0) {
                $checksRun += "invariant_tests: PASSED"
                Write-Host "[OK] Invariant tests passed"
            } else {
                $checksRun += "invariant_tests: FAILED (exit code $invariantExitCode)"
                Write-Host "[FAILED] Invariant tests failed (exit code $invariantExitCode)"
                Write-Host "[CRITICAL] Governance invariants violated - pipeline must fail"
            }
        } else {
            $checksSkipped += "pytest: Not installed or not available"
            Write-Host "[SKIPPED] pytest not available"
        }
    } catch {
        $checksSkipped += "pytest: Error checking availability - $($_.Exception.Message)"
        Write-Host "[SKIPPED] pytest check failed: $($_.Exception.Message)"
    }
    
    # Check for black (formatter)
    try {
        $blackCheck = python -m black --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[RUNNING] black format check..."
            python -m black --check project_guardian/ extracted_modules/ 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                $checksRun += "black: PASSED"
                Write-Host "[OK] black format check passed"
            } else {
                $checksRun += "black: FAILED (formatting issues)"
                Write-Host "[FAILED] black format check failed"
            }
        } else {
            $checksSkipped += "black: Not installed (commented in requirements.txt)"
            Write-Host "[SKIPPED] black not installed"
        }
    } catch {
        $checksSkipped += "black: Not available"
        Write-Host "[SKIPPED] black not available"
    }
    
    # Check for pylint
    try {
        $pylintCheck = python -m pylint --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[RUNNING] pylint check..."
            python -m pylint project_guardian/ --errors-only 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                $checksRun += "pylint: PASSED"
                Write-Host "[OK] pylint check passed"
            } else {
                $checksRun += "pylint: FAILED (linting issues)"
                Write-Host "[FAILED] pylint check failed"
            }
        } else {
            $checksSkipped += "pylint: Not installed (commented in requirements.txt)"
            Write-Host "[SKIPPED] pylint not installed"
        }
    } catch {
        $checksSkipped += "pylint: Not available"
        Write-Host "[SKIPPED] pylint not available"
    }
    
    # Check for mypy
    try {
        $mypyCheck = python -m mypy --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[RUNNING] mypy type check..."
            python -m mypy project_guardian/ --ignore-missing-imports 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                $checksRun += "mypy: PASSED"
                Write-Host "[OK] mypy type check passed"
            } else {
                $checksRun += "mypy: FAILED (type errors)"
                Write-Host "[FAILED] mypy type check failed"
            }
        } else {
            $checksSkipped += "mypy: Not installed (commented in requirements.txt)"
            Write-Host "[SKIPPED] mypy not installed"
        }
    } catch {
        $checksSkipped += "mypy: Not available"
        Write-Host "[SKIPPED] mypy not available"
    }
}

# Node.js checks
if ($isNodeProject) {
    Write-Host ""
    Write-Host "--- Node.js Checks ---"
    
    # Check for npm/yarn/pnpm
    $packageManager = $null
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        $packageManager = "npm"
    } elseif (Get-Command yarn -ErrorAction SilentlyContinue) {
        $packageManager = "yarn"
    } elseif (Get-Command pnpm -ErrorAction SilentlyContinue) {
        $packageManager = "pnpm"
    }
    
    if ($packageManager) {
        Write-Host "[DETECTED] Package manager: $packageManager"
        
        # Check for lint script
        if ($packageJson.scripts.lint) {
            Write-Host "[RUNNING] $packageManager run lint..."
            & $packageManager run lint 2>&1
            if ($LASTEXITCODE -eq 0) {
                $checksRun += "$packageManager lint: PASSED"
                Write-Host "[OK] lint passed"
            } else {
                $checksRun += "$packageManager lint: FAILED"
                Write-Host "[FAILED] lint failed"
            }
        } else {
            $checksSkipped += "lint: No lint script in package.json"
            Write-Host "[SKIPPED] No lint script configured"
        }
        
        # Check for test script
        if ($packageJson.scripts.test) {
            Write-Host "[RUNNING] $packageManager run test..."
            & $packageManager run test 2>&1
            if ($LASTEXITCODE -eq 0) {
                $checksRun += "$packageManager test: PASSED"
                Write-Host "[OK] test passed"
            } else {
                $checksRun += "$packageManager test: FAILED"
                Write-Host "[FAILED] test failed"
            }
        } else {
            $checksSkipped += "test: No test script in package.json"
            Write-Host "[SKIPPED] No test script configured"
        }
        
        # Check for format script
        if ($packageJson.scripts.format) {
            Write-Host "[RUNNING] $packageManager run format..."
            & $packageManager run format 2>&1
            if ($LASTEXITCODE -eq 0) {
                $checksRun += "$packageManager format: PASSED"
                Write-Host "[OK] format passed"
            } else {
                $checksRun += "$packageManager format: FAILED"
                Write-Host "[FAILED] format failed"
            }
        } else {
            $checksSkipped += "format: No format script in package.json"
            Write-Host "[SKIPPED] No format script configured"
        }
    } else {
        $checksSkipped += "Node.js: No package manager (npm/yarn/pnpm) found"
        Write-Host "[SKIPPED] No package manager available"
    }
}

# Summary
Write-Host ""
Write-Host "========================================"
Write-Host "Summary"
Write-Host "========================================"
Write-Host ""

if ($checksRun.Count -gt 0) {
    Write-Host "Checks Executed:"
    foreach ($check in $checksRun) {
        Write-Host "  - $check"
    }
    Write-Host ""
}

if ($checksSkipped.Count -gt 0) {
    Write-Host "Checks Skipped:"
    foreach ($check in $checksSkipped) {
        Write-Host "  - $check"
    }
    Write-Host ""
}

if ($checksRun.Count -eq 0 -and $checksSkipped.Count -eq 0) {
    Write-Host "[INFO] No tooling detected. This is OK - pipeline will not fail."
    Write-Host "       Configure pytest, black, pylint, or npm scripts to enable checks."
    Write-Host ""
    Write-Host "Acceptance runner completed (exit code 0 - no tooling)"
    exit 0
}

# Determine exit code: fail if pytest or invariants failed
$finalExitCode = 0
Write-Host ""
if ($pytestExitCode -ne 0 -or $invariantExitCode -ne 0) {
    Write-Host "[FAILURE] Pipeline failed - tests or invariants failed"
    Write-Host "Exit codes: pytest=$pytestExitCode, invariants=$invariantExitCode"
    $finalExitCode = 1
} else {
    Write-Host "[SUCCESS] Acceptance runner completed (exit code 0)"
    $finalExitCode = 0
}

# Write acceptance artifacts
$endTime = Get-Date
$duration = ($endTime - $startTime).TotalSeconds

# Build summary output for log
$fullOutput = @()
$fullOutput += "========================================"
$fullOutput += "Elysia Acceptance Runner"
$fullOutput += "========================================"
$fullOutput += ""
$fullOutput += "Start Time: $($startTime.ToString('yyyy-MM-dd HH:mm:ss'))"
$fullOutput += "End Time: $($endTime.ToString('yyyy-MM-dd HH:mm:ss'))"
$fullOutput += "Duration: $([math]::Round($duration, 2)) seconds"
$fullOutput += ""
$fullOutput += "Exit Code: $finalExitCode"
$fullOutput += "Status: $(if ($finalExitCode -eq 0) { 'PASS' } else { 'FAIL' })"
$fullOutput += ""
$fullOutput += "Checks Run: $($checksRun.Count)"
foreach ($check in $checksRun) {
    $fullOutput += "  - $check"
}
$fullOutput += ""
$fullOutput += "Checks Skipped: $($checksSkipped.Count)"
foreach ($check in $checksSkipped) {
    $fullOutput += "  - $check"
}
$fullOutput += ""
if ($pytestOutput) {
    $fullOutput += "--- pytest output ---"
    $fullOutput += $pytestOutput
}
if ($invariantOutput) {
    $fullOutput += "--- invariant tests output ---"
    $fullOutput += $invariantOutput
}

# Redact sensitive patterns from output (basic protection)
function Redact-Sensitive {
    param([string]$text)
    # Redact common sensitive patterns
    $patterns = @(
        @{Pattern = '(?i)(api[_-]?key\s*[:=]\s*)([^\s"''\n]+)'; Replacement = '$1[REDACTED]'},
        @{Pattern = '(?i)(password\s*[:=]\s*)([^\s"''\n]+)'; Replacement = '$1[REDACTED]'},
        @{Pattern = '(?i)(token\s*[:=]\s*)([^\s"''\n]+)'; Replacement = '$1[REDACTED]'},
        @{Pattern = '(?i)(secret\s*[:=]\s*)([^\s"''\n]+)'; Replacement = '$1[REDACTED]'},
        @{Pattern = '(?i)(auth[_-]?token\s*[:=]\s*)([^\s"''\n]+)'; Replacement = '$1[REDACTED]'}
    )
    
    $redacted = $text
    foreach ($pattern in $patterns) {
        $redacted = $redacted -replace $pattern.Pattern, $pattern.Replacement
    }
    return $redacted
}

# Write JSON artifact
$acceptanceJson = @{
    timestamp = $endTime.ToString('yyyy-MM-ddTHH:mm:ssZ')
    exit_code = $finalExitCode
    status = if ($finalExitCode -eq 0) { "pass" } else { "fail" }
    duration_seconds = [math]::Round($duration, 2)
    pytest_exit_code = $pytestExitCode
    invariant_exit_code = $invariantExitCode
    checks_run = $checksRun.Count
    checks_skipped = $checksSkipped.Count
} | ConvertTo-Json -Compress

$jsonPath = Join-Path $reportsDir "acceptance_last.json"
$acceptanceJson | Out-File -FilePath $jsonPath -Encoding utf8 -NoNewline

# Assert artifact was written (fail if missing)
if (-not (Test-Path $jsonPath)) {
    Write-Host "[CRITICAL] Acceptance artifact not written: $jsonPath" -ForegroundColor Red
    Write-Host "Acceptance runner failed - artifact assertion failed"
    exit 1
}

# Write log artifact (redacted)
$logPath = Join-Path $reportsDir "acceptance_last.log"
$logContent = ($fullOutput -join "`n") + "`n`n[Note: Sensitive patterns have been redacted]"
$redactedLog = Redact-Sensitive $logContent
$redactedLog | Out-File -FilePath $logPath -Encoding utf8

Write-Host ""
Write-Host "Acceptance artifacts written:"
Write-Host "  - $jsonPath"
Write-Host "  - $logPath"

exit $finalExitCode
