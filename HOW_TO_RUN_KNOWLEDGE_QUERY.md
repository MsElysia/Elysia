# How to Run Full Knowledge Query

## Simple Command

Just run this in your terminal:

```bash
python query_elysia_knowledge.py
```

## What It Does

The script will:
1. Load Elysia's memory system
2. Search for all learned content
3. Categorize by type (Reddit, Web, Financial, LLM Research, etc.)
4. Show statistics and summaries
5. Display recent learning activity

## Expected Output

You'll see:
- ✅ Memory system loaded
- ✅ Found X recent memories
- Categorized content:
  - 📚 Reddit Learning: X items
  - 📚 Web Articles: X items
  - 📚 Financial Learning: X items
  - 📚 LLM Research: X items
- Statistics by source
- Recent learning activity samples

## If It Doesn't Work

If you get errors, try:

1. **Check if GuardianCore is available:**
   ```bash
   python -c "from project_guardian.core import GuardianCore; print('OK')"
   ```

2. **Check the learning session log instead:**
   ```bash
   python monitor_learning_session.py
   ```

3. **View log directly:**
   ```powershell
   Get-Content elysia_learning_session.log
   ```

## Alternative: Quick Summary

For a faster overview:
```bash
python learning_summary.py
```

## Alternative: Search Specific Topics

To search for specific things Elysia learned:
```bash
python search_elysia_knowledge.py "autonomous AI"
```

---

**Just run:** `python query_elysia_knowledge.py`















