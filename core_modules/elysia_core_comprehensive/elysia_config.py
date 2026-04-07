# elysia_core_comprehensive/elysia_config.py — use environment variables for secrets (never commit real keys).
import os

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
POE_ACCESS_TOKEN = os.environ.get("POE_ACCESS_TOKEN", "")
