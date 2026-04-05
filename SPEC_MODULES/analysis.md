# AnalysisEngine Module Specification

## Purpose

The `AnalysisEngine` module provides **read-only analytical capabilities** for Project Guardian. It performs analysis on files, repositories, and URLs **without any mutations, subprocess execution, or writes outside REPORTS/**.

This is Elysia's first "real job" that produces value without risk.

## Module Location

`project_guardian/analysis_engine.py`

## Class: AnalysisEngine

### Initialization

```python
AnalysisEngine(
    memory: MemoryCore,
    web_reader: Optional[WebReader] = None,
    repo_root: Optional[Path] = None
)
```

**Parameters:**
- `memory`: MemoryCore instance for logging analysis events
- `web_reader`: Optional WebReader instance (required for URL_RESEARCH)
- `repo_root`: Optional repository root path (defaults to project root)

**Behavior:**
- If `repo_root` is None, computes from `__file__` location (goes up from `project_guardian/analysis_engine.py` to project root)
- Stores `repo_root` as resolved Path for path safety checks

### Method: run()

```python
def run(kind: str, inputs: List[Dict[str, str]], task_id: Optional[str] = None) -> Dict[str, Any]
```

**Parameters:**
- `kind`: Analysis kind (`REPO_SUMMARY`, `FILE_SET`, `URL_RESEARCH`)
- `inputs`: List of input dicts with `type` and `value` keys
- `task_id`: Optional task ID for audit logging

**Returns:**
- Dict with analysis results (structure depends on `kind`)

**Raises:**
- `ValueError`: If `kind` is unknown or inputs invalid
- `TrustDeniedError`: If network access denied (for URL_RESEARCH)
- `TrustReviewRequiredError`: If network access requires review (for URL_RESEARCH)

**Behavior:**
- Routes to appropriate analysis method based on `kind`
- All analysis methods are read-only (no mutations, no writes)

## Analysis Kinds

### REPO_SUMMARY

**Purpose:** Analyze repository structure and statistics.

**Inputs:**
- `type: "repo"` (value is ignored, typically ".")

**Output:**
```python
{
    "kind": "REPO_SUMMARY",
    "file_counts_by_extension": Dict[str, int],  # Extension -> count
    "total_lines_estimate": int,  # Rough line count
    "top_level_directories": List[str],  # Sorted list
    "timestamp": str,  # ISO format with Z
    "repo_root": str  # Repository root path
}
```

**Behavior:**
- Walks `repo_root` recursively
- Excludes: `venv`, `__pycache__`, `.git`, `node_modules`, `REPORTS`, `TASKS`, `MUTATIONS`, `guardian_backups`
- Counts files by extension (empty string for no extension)
- Estimates LOC by reading first 10KB of each file and counting newlines
- Lists top-level directories (excluding excluded dirs)
- Handles binary files and permission errors gracefully

**Safety:**
- Read-only filesystem access (no writes)
- No TrustMatrix required (filesystem reads are safe)

### FILE_SET

**Purpose:** Analyze specific files (metadata, hash, preview).

**Inputs:**
- `type: "file"`, `value: "<relative_path>"` (one or more)

**Output:**
```python
{
    "kind": "FILE_SET",
    "files": List[Dict[str, Any]],  # One dict per file
    "timestamp": str  # ISO format with Z
}
```

Each file dict:
```python
{
    "filename": str,  # Original input path
    "status": "success" | "not_found" | "error",
    "size_bytes": int,  # If success
    "sha256": str,  # If success
    "preview_lines": List[str],  # First 50 lines (or less)
    "preview_line_count": int,  # Number of preview lines
    "error": str  # If error/not_found
}
```

**Behavior:**
- Resolves each file path relative to `repo_root`
- **Path safety**: Ensures path is within `repo_root` (rejects `..` traversal)
- Computes SHA256 hash (reads file in 8KB chunks)
- Reads first 50 lines for preview (handles binary files gracefully)
- Returns "not_found" status if file doesn't exist or is not a file
- Returns "error" status if read fails

**Safety:**
- Path validation prevents traversal attacks
- Read-only filesystem access
- No TrustMatrix required (filesystem reads are safe)

### URL_RESEARCH

**Purpose:** Analyze web content via WebReader.

**Inputs:**
- `type: "url"`, `value: "<url>"` (one or more)

**Output:**
```python
{
    "kind": "URL_RESEARCH",
    "urls": List[Dict[str, Any]],  # One dict per URL
    "timestamp": str  # ISO format with Z
}
```

Each URL dict:
```python
{
    "url": str,  # Original URL
    "status": "success",
    "content_length": int,  # Length of fetched content
    "preview_chars": str,  # First 1000 characters
    "preview_length": int  # Length of preview
}
```

**Behavior:**
- Uses `WebReader.fetch()` for each URL
- Subject to TrustMatrix gating (may raise `TrustDeniedError` or `TrustReviewRequiredError`)
- Subject to SSRF safety rules (internal targets blocked by default)
- Extracts first 1000 characters for preview
- **Re-raises** trust exceptions (does not catch them) so Core can handle appropriately

**Safety:**
- Network access ONLY via WebReader gateway
- TrustMatrix gating enforced
- SSRF protection enforced
- No partial results on deny/review (exception raised immediately)

## Safety Guarantees

### What AnalysisEngine DOES:
- ✅ Read files from filesystem
- ✅ Call WebReader.fetch() for network access
- ✅ Return analysis results as dicts
- ✅ Log analysis events to MemoryCore

### What AnalysisEngine DOES NOT:
- ❌ Write files (except via Core to REPORTS/)
- ❌ Use FileWriter gateway
- ❌ Use SubprocessRunner gateway
- ❌ Create backups
- ❌ Mutate repository files
- ❌ Write outside REPORTS/ (Core handles report writing)

## Integration with Core

1. **Core calls** `AnalysisEngine.run(kind, inputs, task_id)`
2. **AnalysisEngine performs** read-only analysis
3. **If network access needed** (URL_RESEARCH):
   - WebReader.fetch() gates through TrustMatrix
   - May raise `TrustDeniedError` or `TrustReviewRequiredError`
   - AnalysisEngine re-raises these exceptions
4. **Core catches** exceptions and:
   - Returns `{status: "denied"}` for TrustDeniedError
   - Returns `{status: "needs_review"}` for TrustReviewRequiredError
   - **Does NOT write report** on deny/review
5. **On success**, Core writes report atomically to REPORTS/

## Constants

- `MAX_PREVIEW_LINES = 50`: Maximum lines in FILE_SET preview
- `EXCLUDED_DIRS`: Set of directories excluded from REPO_SUMMARY walk

## Error Handling

- **Unknown kind**: Raises `ValueError`
- **Missing WebReader for URL_RESEARCH**: Raises `ValueError`
- **Network deny**: Re-raises `TrustDeniedError` (Core handles)
- **Network review**: Re-raises `TrustReviewRequiredError` (Core handles)
- **File read errors**: Returns error status in file dict (does not raise)

## Testing

See `tests/test_read_only_analysis_task.py` for comprehensive test coverage:
- REPO_SUMMARY creates report
- FILE_SET reads only (no mutations)
- URL_RESEARCH review creates no report
- URL_RESEARCH deny creates no report
- Invalid contract rejection
- No FileWriter usage
- No SubprocessRunner usage
