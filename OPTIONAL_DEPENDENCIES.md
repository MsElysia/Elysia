# Optional Dependencies and Capability Flags

## Overview

Project Guardian / Elysia uses several optional dependencies to enhance functionality. When these are not installed, the system falls back to basic implementations with reduced capabilities.

## Capability Detection

The system automatically detects available optional dependencies and reports them in the status screen. Check capabilities via:

```python
from project_guardian.capabilities import get_capabilities, format_capabilities_text
capabilities = get_capabilities()
print(format_capabilities_text(capabilities))
```

Or view in the interface: **"View System Status"** option.

## Optional Dependencies

### 1. Sentence Transformers (High-Quality Embeddings)

**Package:** `sentence-transformers`

**Impact:** Enables high-quality local embeddings for semantic search without API calls.

**Installation:**
```bash
# Quick install (recommended - includes faiss, psutil)
pip install -r requirements-optional.txt

# Or just sentence-transformers
pip install sentence-transformers
```

**Note:** Requires PyTorch. If PyTorch is not installed, it will be installed automatically. On some systems, you may need:
```bash
pip install torch torchvision torchaudio
pip install sentence-transformers
```

**Python Version:** Python 3.8+

**Fallback:** Simple TF-IDF-like embedding (lower quality)

**When to Install:**
- You want better semantic search quality
- You want to avoid API costs for embeddings
- You're doing memory-intensive semantic operations

---

### 2. FAISS (Fast Vector Search)

**Package:** `faiss-cpu` (or `faiss-gpu` for GPU support)

**Impact:** Enables efficient vector similarity search for memory retrieval.

**Installation:**
```bash
# CPU version (recommended for most users)
pip install faiss-cpu

# GPU version (if you have CUDA)
pip install faiss-gpu
```

**Windows Caveats:**
- On Windows, you may need Visual C++ Build Tools
- If installation fails, try: `pip install --upgrade pip setuptools wheel`
- Consider using conda: `conda install -c pytorch faiss-cpu`

**Python Version:** Python 3.8+

**Fallback:** In-memory vector storage (slower for large datasets)

**When to Install:**
- You have large memory datasets (>1000 memories)
- You need fast similarity search
- You're using vector memory features

---

### 3. HTTPX (Modern HTTP Client)

**Package:** `httpx`

**Impact:** Enables web research and URL fetching capabilities.

**Installation:**
```bash
pip install httpx
```

**Python Version:** Python 3.8+

**Fallback:** Limited web reading capabilities

**When to Install:**
- You want to use WebScout agent
- You need web research features
- You're using URL fetching

---

### 4. Playwright (Browser Automation)

**Package:** `playwright`

**Impact:** Enables rendering of JavaScript-heavy dynamic web pages.

**Installation:**
```bash
pip install playwright
playwright install
```

**Important:** After `pip install playwright`, you **must** run `playwright install` to download browser binaries.

**Python Version:** Python 3.8+

**Fallback:** Static HTML only (no JavaScript rendering)

**When to Install:**
- You need to scrape JavaScript-heavy sites
- You're doing advanced web research

---

### 5. PSUtil (System Monitoring)

**Package:** `psutil`

**Impact:** Enables system resource monitoring (CPU, memory, disk).

**Installation:**
```bash
pip install psutil
```

**Python Version:** Python 3.6+

**Fallback:** Limited system monitoring

**When to Install:**
- You want system resource monitoring
- You're using auto-cleanup features
- You need performance metrics

---

### 6. Anthropic SDK (Claude API)

**Package:** `anthropic`

**Impact:** Enables Claude API access for AI interactions.

**Installation:**
```bash
pip install anthropic
```

**Python Version:** Python 3.8+

**Fallback:** Claude API unavailable

**When to Install:**
- You want to use Claude API
- You have ANTHROPIC_API_KEY configured

---

### 7. OpenAI SDK (OpenAI API)

**Package:** `openai`

**Impact:** Enables OpenAI API access (GPT-4, etc.).

**Installation:**
```bash
pip install openai
```

**Python Version:** Python 3.8+

**Fallback:** OpenAI API unavailable

**When to Install:**
- You want to use OpenAI API
- You have OPENAI_API_KEY configured

---

## Python Version Recommendations

**Recommended:** Python 3.11 or 3.12

**Why:**
- Best compatibility with all optional dependencies
- Stable and well-tested
- Good performance
- All packages have wheels available

**Python 3.13:**
- May have compatibility issues with some packages
- Some packages may not have wheels available yet
- If you encounter issues, consider Python 3.11 or 3.12

**Python 3.8-3.10:**
- Supported but older
- Some newer features may not be available
- Some packages may have limited support

## Installation Profiles

### Minimal Recommended

For basic functionality with improved embeddings and search:

```bash
pip install sentence-transformers faiss-cpu psutil
```

### Full (All Features)

For maximum functionality:

```bash
pip install sentence-transformers faiss-cpu httpx playwright psutil anthropic openai
playwright install
```

### With GPU Support

If you have CUDA and want GPU acceleration:

```bash
pip install sentence-transformers faiss-gpu httpx playwright psutil anthropic openai
playwright install
```

## Checking Capabilities

### In Code:
```python
from project_guardian.capabilities import get_capabilities, format_capabilities_text

# Get detailed report
capabilities = get_capabilities()
for name, info in capabilities.items():
    status = "[OK]" if info["available"] else "[MISSING]"
    version = info["version"] or "N/A"
    print(f"{status} {name}: {version} - {info['notes']}")

# Get formatted summary
print(format_capabilities_text(capabilities))
```

### In Interface:
1. Run `python elysia_interface.py`
2. Choose option **"1" - View System Status**
3. Scroll to **"Capabilities"** section

### Via Status API:
```python
from project_guardian.core import GuardianCore
core = GuardianCore()
status = core.get_system_status()
capabilities = status['capabilities']
```

## Impact of Missing Dependencies

| Dependency | Impact When Missing |
|------------|---------------------|
| sentence-transformers | Lower quality embeddings, fallback to simple TF-IDF |
| faiss | Slower vector search, in-memory storage only |
| httpx | Limited web research, no WebScout agent |
| playwright | No JavaScript rendering for web pages |
| psutil | Limited system monitoring, no resource metrics |
| anthropic | Claude API unavailable |
| openai | OpenAI API unavailable |

## Troubleshooting

### Installation Issues

**sentence-transformers:**
- If installation fails, try: `pip install --upgrade pip setuptools wheel`
- On Windows, may need Visual C++ Build Tools
- PyTorch may need to be installed separately on some systems

**faiss-cpu:**
- If installation fails, try: `pip install --upgrade pip`
- On Windows, may need Visual C++ Build Tools
- Consider using conda: `conda install -c pytorch faiss-cpu`
- On macOS, may need: `brew install libomp`

**playwright:**
- After `pip install playwright`, must run: `playwright install`
- This downloads browser binaries (can be large)
- If download fails, check network connection

### Python 3.13 Issues

If you encounter issues with Python 3.13:

1. **Try Python 3.11 or 3.12:**
   ```bash
   # Using pyenv or similar
   pyenv install 3.11.9
   pyenv local 3.11.9
   ```

2. **Use virtual environment:**
   ```bash
   python3.11 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Check package compatibility:**
   - Some packages may not have Python 3.13 wheels yet
   - Check package documentation for Python 3.13 support
   - Consider waiting for package updates

## Verification

After installing dependencies, verify they're detected:

```python
from project_guardian.capabilities import get_capabilities
caps = get_capabilities()
for name, info in caps.items():
    if info["available"]:
        print(f"[OK] {name}: {info['version']}")
```

Or check in the system status screen - capabilities should show as `[OK]` for installed packages.
