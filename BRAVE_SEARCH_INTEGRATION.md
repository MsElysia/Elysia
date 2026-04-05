# Brave Search API Integration

## Summary

Successfully integrated **Brave Search API** into Elysia's WebScout agent with rate limiting and usage tracking.

## Features

✅ **Brave Search API Integration** - Real web search capability  
✅ **Rate Limiting** - Tracks usage to stay within 2000 requests/month limit  
✅ **Usage Tracking** - Persistent tracking across restarts  
✅ **Automatic Monthly Reset** - Resets counter at start of each month  
✅ **Warning System** - Warns at 80% and 95% usage  
✅ **Usage Statistics** - Get current usage via `get_brave_search_usage()`

## API Key Storage

The Brave Search API key is stored in:
- `API keys/brave search api key.txt` ✅ (Already saved)
- Environment variable: `BRAVE_SEARCH_API_KEY`
- Config file: `config/api_keys.json` (under `brave_search.api_key`)

## Rate Limiting

**Limit:** 2000 requests per month

**Tracking:**
- Usage stored in `config/brave_search_usage.json`
- Automatically resets at start of each month
- Tracks requests per month with timestamp

**Warnings:**
- 80% usage (1600 requests): Warning logged
- 95% usage (1900 requests): Error logged, searches blocked
- 100% usage (2000 requests): All searches blocked until next month

## Usage

### Automatic Usage

When WebScout conducts research, it will:
1. Check if Brave Search API key is available
2. Check current usage against limit
3. If under limit, perform search and increment counter
4. If at limit, fall back to LLM-only research

### Check Usage

```python
from project_guardian.webscout_agent import ElysiaWebScout

webscout = ElysiaWebScout()
usage = webscout.get_brave_search_usage()

print(f"Requests used: {usage['requests_used']}/{usage['requests_limit']}")
print(f"Remaining: {usage['requests_remaining']}")
print(f"Percentage: {usage['percentage_used']}%")
print(f"Can use: {usage['can_use']}")
```

### Manual Search

```python
urls = webscout._brave_search("Python async patterns", count=10)
# Returns list of URLs from Brave Search
# Automatically tracks usage
```

## Implementation Details

### Usage Tracking File

Location: `config/brave_search_usage.json`

Format:
```json
{
  "current_month": "2025-11",
  "requests_this_month": 42,
  "last_reset": "2025-11-01T00:00:00"
}
```

### Rate Limit Check

The `_check_brave_search_limit()` method:
- Returns `(can_use, current_usage, limit)`
- Automatically resets if new month detected
- Logs warnings at 80% and 95%

### Increment Usage

The `_increment_brave_search_usage()` method:
- Increments counter only on successful API calls
- Saves to disk immediately
- Does NOT increment on errors (rate limit errors, network errors, etc.)

## Best Practices

1. **Monitor Usage** - Check usage regularly with `get_brave_search_usage()`
2. **Batch Searches** - Group related queries to minimize API calls
3. **Cache Results** - Consider caching search results for repeated queries
4. **Fallback Gracefully** - System falls back to LLM-only research when limit reached

## Status

✅ **Fully Integrated** - Brave Search API is ready to use!

The WebScout agent will now:
1. Use Brave Search to find relevant URLs for research queries
2. Track usage to stay within 2000/month limit
3. Warn when approaching limit
4. Block searches when limit reached
5. Fall back to LLM-only research when needed

This provides real web search capability while respecting API limits.

