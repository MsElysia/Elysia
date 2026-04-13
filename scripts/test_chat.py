#!/usr/bin/env python3
"""
Quick test for Elysia chat endpoint.
Run while Elysia backend is running. Usage:
  python scripts/test_chat.py
  python scripts/test_chat.py "Your message here"
"""
import sys
import json
import urllib.request

STATUS_URL = "http://127.0.0.1:8888"
CHAT_URL = f"{STATUS_URL}/chat"


def test_chat(message: str = "Hello, can you respond?") -> bool:
    try:
        data = json.dumps({"message": message}).encode("utf-8")
        req = urllib.request.Request(
            CHAT_URL,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            out = json.loads(r.read().decode())
        reply = out.get("reply", "")
        err = out.get("error", "")
        if err:
            print(f"[ERROR] {err}")
            if "API key" in err.lower() or "openai" in err.lower() or "openrouter" in err.lower():
                print("       -> Check API keys in the 'API keys' folder (chat gpt api key for elysia.txt, etc.)")
            return False
        print(f"[OK] Reply: {reply[:200]}{'...' if len(reply) > 200 else ''}")
        return True
    except urllib.error.URLError as e:
        print(f"[FAIL] Cannot reach {CHAT_URL}")
        print(f"       {e}")
        print("       -> Start Elysia first (e.g. Start Project Guardian.bat or python elysia.py)")
        return False
    except Exception as e:
        print(f"[FAIL] {e}")
        return False


def main():
    msg = sys.argv[1] if len(sys.argv) > 1 else "Hello, can you respond?"
    print("Testing Elysia chat endpoint...")
    print(f"  URL: {CHAT_URL}")
    print(f"  Message: {msg}")
    print()
    ok = test_chat(msg)
    print()
    print("Chat test PASSED" if ok else "Chat test FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
