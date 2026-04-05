# Auto-Learning

Elysia gathers data from the web on AI, income, and other topics, compresses it with the LLM, and stores it on the thumb drive.

## How It Works

- **Schedule:** Runs every 6 hours (configurable)
- **Sources:**
  - **ChatGPT conversations** from `F:\ProjectGuardian\memory\personal\chatlogs\` (files from `import_chatgpt_export.py`)
  - **Reddit** (r/MachineLearning, r/passive_income, etc.)
  - **RSS feeds** (TechCrunch, Wired, ML Mastery)
- **Compression:** Uses OpenAI/OpenRouter to summarize each item when API keys are available
- **Storage:** `F:\ProjectGuardian\memory\learned\learned_YYYY-MM-DD.jsonl` on the thumb drive
- **Tracking:** Processed ChatGPT files are logged in `.processed_chatlogs.json` so they aren't re-read every run

## Configuration

**Environment variables:**
- `ELYSIA_AUTO_LEARNING=true` — Enable (default: true)
- `ELYSIA_LEARNING_INTERVAL_HOURS=6` — Hours between runs (default: 6)

**Config file:** `config/auto_learning.json`

```json
{
  "enabled": true,
  "interval_hours": 6,
  "topics": ["AI", "income", "automation", ...],
  "reddit_subs": ["MachineLearning", "passive_income", ...],
  "rss_feeds": ["https://feeds.feedburner.com/TechCrunch", ...]
}
```

Add or remove subreddits and RSS feeds to change what Elysia learns.

## Output Format

Each line in `learned_YYYY-MM-DD.jsonl` is a JSON object:
- `source`, `title`, `text`, `url`, `compressed` (LLM summary or truncation), `learned_at`
