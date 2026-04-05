# How to Find Out What Elysia Learned 📚

## Quick Methods

### 1. **Query All Learned Knowledge** (Recommended)
```bash
python query_elysia_knowledge.py
```
This shows:
- All learned content organized by category
- Statistics (Reddit posts, web articles, financial info, etc.)
- Recent learning activity
- Total items learned

### 2. **Search for Specific Topics**
```bash
python search_elysia_knowledge.py "autonomous AI"
python search_elysia_knowledge.py "machine learning"
python search_elysia_knowledge.py "investment strategies"
```
Search for specific topics Elysia learned about.

### 3. **Check Learning Session Log**
```bash
python monitor_learning_session.py
```
Or view the log directly:
```powershell
# Windows PowerShell
Get-Content elysia_learning_session.log -Wait -Tail 50

# Windows CMD
type elysia_learning_session.log | more

# Linux/Mac
tail -f elysia_learning_session.log
```

## Detailed Methods

### 4. **Access Memory System Directly**

If you're using Python interactively:
```python
from project_guardian.core import GuardianCore

core = GuardianCore()
memory = core.memory

# Get recent memories
recent = memory.recall_last(count=50)

# Search for learning-related content
for mem in recent:
    content = mem.get('thought', mem.get('content', ''))
    tags = mem.get('tags', [])
    
    # Check if it's learning-related
    if any('learning' in str(tag).lower() for tag in tags):
        print(f"Learned: {content[:200]}...")
```

### 5. **Check by Category**

Elysia tags learned content with:
- `web_learning` - Web articles
- `reddit` - Reddit posts
- `financial_learning` - Financial information
- `llm_research` - External AI insights
- `rss_feed` - RSS feed content
- `learning` - General learning
- `knowledge` - Knowledge items

### 6. **View Statistics**

The learning session tracks:
- Total Reddit posts learned
- Total web articles learned
- Total financial sources learned
- Total LLM insights gathered
- Learning cycles completed

## What Elysia Learned

### From Reddit:
- Latest AI discussions
- Machine learning trends
- Autonomous systems discussions
- Community insights

### From Web:
- Tech news articles
- AI research papers
- Industry updates
- Scientific articles

### From Financial Sources:
- Investment strategies
- Market trends
- AI stock information
- Economic insights

### From LLM Research:
- Multi-perspective insights from GPT-4
- Analysis of AI trends
- Research summaries
- Expert opinions

## Example Output

When you run `query_elysia_knowledge.py`, you'll see:

```
📚 Reddit Learning: 45 items
   - Latest discussion on autonomous AI systems...
   - Machine learning trends in 2024...
   - Community insights on AI safety...

📚 Web Articles: 32 items
   - Tech news: Latest AI developments...
   - Research paper summary: Neural networks...
   - Industry update: AI automation...

📚 Financial Learning: 12 items
   - Investment strategies for AI stocks...
   - Market trends in tech sector...
   - Economic impact of AI...

📚 LLM Research: 8 items
   - GPT-4 insights on autonomous systems...
   - Analysis of AI trends...
   - Research perspectives...
```

## Tips

1. **Check the log first** - The learning session log shows real-time activity
2. **Use search** - Search for specific topics you're interested in
3. **Check categories** - Different learning sources are tagged differently
4. **Review statistics** - See overall learning progress

## Files to Check

1. **`elysia_learning_session.log`** - Detailed session log
2. **Memory system** - All learned content stored here
3. **Learning statistics** - Tracked in the session

---

**Quick Start:**
```bash
# See everything Elysia learned
python query_elysia_knowledge.py

# Search for specific topic
python search_elysia_knowledge.py "your topic here"
```

