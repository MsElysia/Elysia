"""
Browser acceptance probe for the Elysia dashboard (Playwright + local Chrome).

Records console errors, page exceptions, failed/non-2xx requests, and the header
status text over time. Optional steps, in order: theme toggle + reload, one
fictional chat message, then stopping the backend to check offline detection.

    python scripts/dashboard_browser_probe.py --url http://127.0.0.1:5055 --out OUT_DIR \
        [--theme-reload] [--chat "hello"] [--interrupt-cmd "..."]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", default="probe")
    ap.add_argument("--seconds", type=float, default=7.0)
    ap.add_argument("--chat", default="")
    ap.add_argument("--theme-reload", action="store_true")
    ap.add_argument("--interrupt-cmd", default="", help="shell command that stops the backend mid-test")
    ap.add_argument("--chrome", default=os.environ.get("CHROME_PATH", "/usr/local/bin/google-chrome"))
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    result = {"url": args.url, "console": [], "page_errors": [], "bad_requests": [], "status_timeline": []}

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.chrome, headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        page.on("console", lambda m: result["console"].append({"type": m.type, "text": m.text}))
        page.on("pageerror", lambda e: result["page_errors"].append(str(e)))
        page.on("requestfailed", lambda r: result["bad_requests"].append(
            {"url": r.url, "failure": r.failure}))
        page.on("response", lambda r: r.status >= 400 and result["bad_requests"].append(
            {"url": r.url, "status": r.status}))

        t0 = time.time()

        def watch(seconds):
            t1 = time.time()
            while time.time() - t1 < seconds:
                txt = page.locator("#status-text").inner_text()
                cls = page.locator("#status-indicator").get_attribute("class")
                last = result["status_timeline"][-1] if result["status_timeline"] else {}
                if last.get("text") != txt or last.get("indicator") != cls:
                    result["status_timeline"].append({"t": round(time.time() - t0, 1), "text": txt, "indicator": cls})
                time.sleep(0.25)

        page.goto(args.url, wait_until="domcontentloaded")
        watch(args.seconds)
        page.screenshot(path=str(out / f"{args.label}_dashboard.png"), full_page=False)
        if page.locator("#model-status").count():
            result["model_card"] = page.locator("#model-status").inner_text()

        if args.theme_reload:
            before = page.evaluate("document.body.getAttribute('data-theme')")
            page.locator(".theme-toggle").click()
            after = page.evaluate("document.body.getAttribute('data-theme')")
            page.reload(wait_until="domcontentloaded")
            result["status_timeline"].append({"t": round(time.time() - t0, 1), "event": "page reloaded"})
            watch(3)
            reloaded = page.evaluate("document.body.getAttribute('data-theme')")
            result["theme"] = {"before": before, "after_toggle": after, "after_reload": reloaded}

        if args.chat:
            page.locator(".tab", has_text="Control").click()
            page.fill("#api-chat-message", args.chat)
            page.locator("#api-chat-message").locator("xpath=following-sibling::button").click()
            try:
                page.wait_for_function(
                    "() => { const t = document.getElementById('api-chat-result').textContent;"
                    " return t && t !== 'Sending...'; }", timeout=150000)
            except Exception as e:
                result["chat_wait_error"] = str(e)
            result["chat_result"] = page.locator("#api-chat-result").inner_text()
            page.locator("#api-chat-result").scroll_into_view_if_needed()
            page.screenshot(path=str(out / f"{args.label}_chat.png"), full_page=False)
            page.locator(".tab", has_text="Dashboard").click()

        if args.interrupt_cmd:
            subprocess.run(args.interrupt_cmd, shell=True, check=False)
            result["status_timeline"].append({"t": round(time.time() - t0, 1), "event": "server interrupted"})
            watch(args.seconds + 3)
            page.screenshot(path=str(out / f"{args.label}_after_interrupt.png"), full_page=False)

        result["logs_panel"] = page.locator("#console-logs").inner_text()[-3000:]
        browser.close()

    (out / f"{args.label}.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
