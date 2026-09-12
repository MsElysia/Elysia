# Cloudflare / CAPTCHA / Turnstile Fail-Closed Triage

## Current checkpoint

**HEAD:** `132eacc fix(tests): repair core task-router contract expectations`

**Date:** 2026-06-03

**Milestone:** Documentation/triage only — no browser behavior implementation, no staging of dirty WebScout/browser files, no autonomy enablement.

---

## Relevant files inspected (committed + dirty status)

| Area | Path | Dirty? |
|------|------|--------|
| Bounded browser agent | `project_guardian/bounded_browser/agent.py` | **Yes** (`M`) |
| Browser backends | `project_guardian/bounded_browser/backends.py` | **Yes** (`M`) |
| Capability entry | `project_guardian/bounded_browser/capability.py` | **Yes** (`M`) |
| Heuristics | `project_guardian/bounded_browser/evaluate.py` | **Yes** (`M`) |
| Session memory | `project_guardian/bounded_browser/memory_store.py` | **Yes** (`M`) |
| Moltbook preset | `project_guardian/bounded_browser/moltbook.py` | **Yes** (`M`) |
| Schema | `project_guardian/bounded_browser/schema.py` | Clean |
| Allowlist | `project_guardian/bounded_browser/allowlist.py` | Clean |
| WebScout (PG) | `project_guardian/webscout_agent.py` | **Yes** (`M`) |
| WebScout (Elysia) | `elysia/agents/webscout.py` | **Yes** (`M`) |
| HTTP gateway | `project_guardian/external.py` (`WebReader`) | Clean |
| Capability router | `project_guardian/capability_execution.py` | Clean (browser dispatch) |
| Tests | `project_guardian/tests/test_bounded_browser.py`, `tests/test_bounded_browser_capability.py` | Clean / separate dirty test trees not staged |
| Social | `project_guardian/social_intelligence/service.py` (moltbook browse hooks) | Clean |

**Search terms (repo, committed HEAD):** no matches for `cloudflare`, `turnstile`, `captcha`, `blocked_by_cloudflare_verification`, or `manual_operator_required` under `project_guardian/bounded_browser`, `elysia/agents/webscout.py`, or `tests/`.

---

## Dirty browser/WebScout files found

Eight paths show `M` in `git status`:

1. `elysia/agents/webscout.py`
2. `project_guardian/webscout_agent.py`
3. `project_guardian/bounded_browser/agent.py`
4. `project_guardian/bounded_browser/backends.py`
5. `project_guardian/bounded_browser/capability.py`
6. `project_guardian/bounded_browser/evaluate.py`
7. `project_guardian/bounded_browser/memory_store.py`
8. `project_guardian/bounded_browser/moltbook.py`

**Not staged in this milestone.** Do not use dirty hunks as proof of fail-closed behavior.

---

## Classification of dirty diffs

| File | Classification | Summary |
|------|----------------|---------|
| `elysia/agents/webscout.py` | **RISKY_BROWSER_AUTONOMY** / **NEEDS_HUMAN_REVIEW** | Large expansion: architecture doc builder, proposal helpers — not Cloudflare-related |
| `project_guardian/webscout_agent.py` | **RISKY_EXECUTION_PATH** / **NEEDS_HUMAN_REVIEW** | LLM JSON research fallback, `get_existing_guardian_core` — not challenge detection |
| `bounded_browser/agent.py` | **RISKY_BROWSER_AUTONOMY** | More links per page, `force_link_follow`, exploratory floor — increases crawl surface |
| `bounded_browser/backends.py` | **RISKY_BROWSER_AUTONOMY** / **NEEDS_HUMAN_REVIEW** | ~155 lines backend changes (no challenge keywords in diff) |
| `bounded_browser/capability.py` | **RISKY_BROWSER_AUTONOMY** | Exposes link budget knobs in compact result |
| `bounded_browser/evaluate.py` | **RISKY_BROWSER_AUTONOMY** | Moltbook-specific link scoring heuristics |
| `bounded_browser/memory_store.py` | **SAFE_TEST_SUPPORT** (intent) | Low-value host TTL expiry — operational, not bypass |
| `bounded_browser/moltbook.py` | **RISKY_BROWSER_AUTONOMY** | Raises page/scroll/depth caps; `MOLTBOOK_FORCE_LINK_FOLLOW = True` |

**Not found in dirty diffs:** `CLOUDFLARE_FAIL_CLOSED_RELATED`, `RISKY_BYPASS_BEHAVIOR`, `RISKY_RETRY_LOOP` (no CAPTCHA bypass or aggressive retry loops added in these hunks).

---

## Current committed behavior summary

### Explicit Cloudflare/CAPTCHA/Turnstile detection

**No.** Committed code does not scan page title/body/URL for challenge indicators or emit `blocked_by_cloudflare_verification`.

### Bounded timeouts (committed)

| Location | Behavior |
|----------|----------|
| `bounded_browser/backends.py` | `open_url(timeout_ms=25_000)` default; Playwright `goto` + optional `networkidle` 8s; urllib `urlopen` clamped **1–30s** via `_timeout_seconds()` |
| `project_guardian/external.py` | `WebReader` HTTP `timeout=10` / `timeout_s=30` |
| `webscout_agent.py` (committed) | Research HTTP calls `timeout_s=10` / `15` |

### Fail-closed blocked result (committed)

**Partial / indirect only:**

- `browse_task` sets `stop_reason` to `navigation_error:…` on `open_url` exception, then **breaks** (no retry loop in agent).
- `run_bounded_browser_for_capability` returns `{"success": True, "result": compact}` even when `stop_reason` is an error string — callers must inspect `stop_reason`.
- No structured fields: `blocked_by_cloudflare_verification`, `manual_operator_required`, `no_retry`, `no_browser_bypass`.

### Retry / bypass (committed)

- **No CAPTCHA/Turnstile/Cloudflare bypass** in committed browser or WebScout paths.
- **No challenge retry loop** in `bounded_browser/agent.py` (single `open_url` attempt per queued URL).
- Autonomy remains **disabled** (`config/autonomy.json` → `"enabled": false`).

---

## Required fail-closed design (implementation baseline — not built in this milestone)

When page title, visible text, or URL indicates a bot-verification / challenge surface:

1. **Detect** (committed + future): match known indicators, e.g.:
   - Title/body: `cloudflare`, `attention required`, `verify you are human`, `checking your browser`, `ray id`
   - Widgets: `cf-turnstile`, `g-recaptcha`, `hcaptcha`, `challenges.cloudflare.com`
   - Turnstile/CAPTCHA copy: `complete the security check`, `captcha`
2. **Stop immediately** — do not scroll, follow links, or enqueue further navigation.
3. **Return bounded blocked payload** (example shape):

```json
{
  "success": false,
  "blocked": true,
  "reason_code": "blocked_by_cloudflare_verification",
  "manual_operator_required": true,
  "no_retry": true,
  "no_browser_bypass": true,
  "stop_reason": "blocked_by_cloudflare_verification"
}
```

4. **Manual operator handoff** — log/audit entry; WebScout/autonomy must not continue through the challenge.
5. **Prohibited:** CAPTCHA automation, Turnstile token injection, cookie replay to bypass, aggressive retries, headless “stealth” bypass.

### Recommended implementation location (next milestone)

| Layer | Path | Rationale |
|-------|------|-----------|
| **Primary** | `project_guardian/bounded_browser/challenge_detection.py` (new) | Pure functions: `detect_verification_challenge(title, text, url) -> Optional[ChallengeBlock]` |
| **Hook** | `project_guardian/bounded_browser/agent.py` | After successful `open_url`, before scroll/link loop: if challenge → set `stop_reason`, return early |
| **Surface** | `project_guardian/bounded_browser/capability.py` | Map challenge block to `success: false` + reason fields for capability/autonomy callers |
| **Optional HTTP** | `project_guardian/external.py` (`WebReader`) | If response body is HTML challenge page, fail-closed before returning content to WebScout (HTTP-only path) |
| **WebScout guard** | `project_guardian/webscout_agent.py` | If research depends on browser HTML, honor blocked result; do not spin alternate fetch loops |
| **Tests** | `project_guardian/tests/test_bounded_browser_challenge_detection.py` (new) | Synthetic fixtures only |

Do **not** implement in dirty unstaged hunks; land via a clean, reviewable commit after this doc.

---

## Test plan (documentation only — no browser runs in triage)

All tests use **FakeBackend** / static HTML strings (same pattern as `test_bounded_browser.py`). **No Playwright, no network, no WebScout execution.**

| Fixture | Input | Expected |
|---------|-------|----------|
| Normal page | Title `Asyncio docs`, body about asyncio | `detect_verification_challenge` → `None`; browse continues |
| Cloudflare interstitial | Title `Just a moment...`, body `Checking your browser`, `Ray ID` | Block with `reason_code=blocked_by_cloudflare_verification` |
| Turnstile | Body contains `cf-turnstile` / `challenges.cloudflare.com` | Block + `manual_operator_required=true` |
| CAPTCHA | Body `g-recaptcha` / `hcaptcha` / “verify you are human” | Block + `no_browser_bypass=true` |
| Capability wrapper | FakeBackend returns challenge HTML on first `open_url` | `run_bounded_browser_for_capability` → `success: false`, `no_retry: true`, no second `open_url` call |
| Regression | Navigation timeout | Still `navigation_error` (unchanged); must not be classified as challenge unless indicators present |

Assert blocked payloads include **`manual_operator_required`** and do not invoke `scroll_once` / `click_link` after detection.

---

## Safety statement

| Check | Status |
|-------|--------|
| Autonomy enabled | **No** (`config/autonomy.json` unchanged, `"enabled": false`) |
| Live execution run | **No** |
| WebScout/browser activity run | **No** (triage used `git diff` + static code read only) |
| API/server routes added | **No** |
| Execution code added | **No** (documentation commit only) |
| Dirty WebScout/browser files staged | **No** |
| CAPTCHA/Cloudflare bypass added | **No** |

---

## Verification at triage time

| Command | Result |
|---------|--------|
| `python scripts/run_elysia_dry_run_report.py --mode real-planning` | SAFE, exit 0 |
| Passive Phase 2 targeted pytest (6 modules) | 92 passed |
| `python scripts/run_safe_stack_smoke_tests.py` | 454 passed |

---

## Related docs

- [`docs/WEBREADER_RUNTIME_TEST_REPAIR.md`](WEBREADER_RUNTIME_TEST_REPAIR.md) — HTTP gateway tests (not browser challenges)
- [`docs/DIRTY_RISKY_HUNKS_TRIAGE.md`](DIRTY_RISKY_HUNKS_TRIAGE.md) — prior risky hunk policy
- [`docs/FULL_RUNTIME_TEST_CLASSIFICATION.md`](FULL_RUNTIME_TEST_CLASSIFICATION.md) — broader test backlog
