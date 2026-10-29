# Local intelligence integration candidate — October 29, 2026

Release: STOP. Local development may continue. This is a runnable extension of the preserved restricted browser candidate, NOT an update to the inaccessible Windows pilot 4f69bd12eaa30f8aa83e3c731359d9c7ea626e50.

## Source and ownership

One integration owner/branch: integration/windows-local-delivery-20261028, based on bd3a1c5d7bfa648501f9e18d589c95b5a32082df. Reused the accessible draft 1d24cc234a622404957b03db90b1a3e6605afa94's context builder, strict transport, and 21 original regression tests; adapted its metadata projection to the existing core_modules/elysia_core_comprehensive/ai_tool_registry.py ToolRegistry. No task-router auto-discovery, legacy provider routing or credential-manager initialization.

The Windows pilot commit remains unavailable locally and GitHub could not resolve it. PRs 156 (b347319a0c32f2f0b005774ea7d4410896a55688), 160 (abaa82abe1be9edcb1f8c7669d18e186d30b2276), and 161 (a09593be4d044f2333aeccbd93159fb95e8433b0) remain separate, open and unmerged at inspection. Their different dashboards/provider paths were not combined here.

## What is connected

The authenticated existing restricted browser now has Ask local model and a per-question calculator checkbox. Host/Origin/session/CSRF guards run before retrieval or inference. The offline worker returns a bounded context bundle from its same durable store: current revisions only, source/chunk/highlight IDs, source hashes, revision numbers and a bundle digest. No extra memory database/index is created.

The host uses that data with the explicitly configured local Ollama model. It supplies at most one prior conversation turn, held in session RAM and cleared after memory writes. The host re-reads the context after generation and discards a response if relevant evidence changed. The answer envelope labels the actual requested/returned model, supplied evidence and executed tools; evidence supplied does not prove model reasoning actually relied on it.

Only calculator.labor has a tool execution binding. A model proposal cannot grant its scope. The operator checkbox grants that scope for one request. The host checks catalog availability, exact argument fields, integer quantity bounds, a current retrieved source, and the narrow fact format below; then runs existing deterministic calculate_local. The result includes the expression, total, source/revision, and assumptions requiring review. Verified arithmetic does not establish that model-selected quantities match user intent.

Finance, email, web, calendar, documents, construction estimates and memory ingestion remain descriptions with unavailable execution. No dynamic Python, shell, network tool dispatch or generic executor is exposed. Memory search is used by the fixed context pipeline; model-proposed memory.search has no execution binding.

## Local transport boundary

Literal 127.0.0.1:11434 by default, no environment URL override, proxies, DNS service names, redirects, retries, downloads or provider fallback. Each request is capped at 65,536 response bytes and a 35-second wall deadline (including trickling responses); connect timeout is 3 seconds. Generation uses /api/tags, /api/show and /api/chat, so the upper network budget is three such requests. Prompt cap: 18,000 UTF-8 bytes. Evidence cap: four complete items / 10,000 serialized bytes. Generation: 512 tokens, context 8192, JSON output. Exact model identity/completion/content checks apply.

Cloud-tagged models and remote_host/remote_model aliases are rejected, and /api/show must establish model architecture metadata before inference. This trusts the local Ollama service's metadata; it is not a sandbox for a compromised daemon. On the Windows host, also configure the Ollama daemon itself with OLLAMA_NO_CLOUD=1 and verify its cloud-disabled startup log. Do not enable cloud services or download a model for this test.

The original network-denying memory-worker guard is unchanged. Inference runs in the authenticated host process, never in the memory worker. No generated claims are persisted. Memory remains a fictional-only bounded pilot with seven learned revisions; this candidate must not be pointed at personal or production memory.

## Start an isolated candidate (native Windows execution NOT yet verified)

Use a new extraction directory, Python 3.12+ and an existing interpreter with Flask installed. Do not overwrite the working 5066 pilot or use legacy port 5065. If 5077 is occupied, choose another unused unprivileged port explicitly. Select an already-installed genuinely local model; the example name is not a claim about the current host inventory.

```powershell
python -B elysia_restricted_browser.py --port 5077 --store localchat --local-model qwen3:4b
```

Enter a temporary password at the terminal; open http://127.0.0.1:5077/ and authenticate. The model is discovered/validated on request; no model is started or downloaded automatically. Omitting --local-model preserves memory functionality and returns a truthful chat-not-configured error. Ctrl+C ends this candidate; ownership is released through the existing runtime-owner context.

Save key rate with this exact synthetic fact:

```text
Fictional labor rate is USD 35 per hour.
```

Check Allow the labor calculator, then ask:

```text
Use my saved labor rate to estimate the labor expense for two painters working three eight-hour days.
```

Expected deterministic total: USD 1680, with 2 × 3 × 8 × 35, source and revision. Review the model-selected quantities. Correct the fact to USD 40 per hour and repeat: USD 1920 with revision 2. Restart the candidate and confirm revision 2 remains. Uncheck calculator: a model calculator proposal must be refused, with no execution.

Also ask an unfamiliar general question and a memory-dependent question. A real installed model must supply original text before marking these gates passed. Request email/web/finance tools and confirm unavailable/no execution. Stop only the test Ollama instance if independently owned, or test an unavailable service in an isolated fixture; never terminate unrelated user processes. Model failure must return an error and recall must still work.

## Verification and acceptance

Run from candidate source with the disposable test interpreter:

```text
python -B -m pytest --noconftest tests/test_local_chat_http.py tests/test_local_chat_integration.py tests/test_local_memory_chat.py tests/test_restricted_browser_bridge.py tests/test_delivery_runtime.py -q -p no:cacheprovider
```

The HTTP probe opens a real loopback application listener and calls the actual registered routes, guarded subprocess memory worker, direct HTTP transport and calculator. Its model peer is explicitly synthetic. It proves wiring and failure handling, not real model intelligence. It also checks a trickling response hits the absolute deadline. Fixtures use temporary source-only stores and disposable ports.

Independent review found transport error masking, overclaimed answer verification, cloud-alias uncertainty, unbounded trickling-response duration, and insufficient rate-role validation. Those paths were corrected and have focused regressions. The reviewer did not verify final edited source on Windows or with real Ollama.

Acceptance status:
- A, original actual-model response: UNVERIFIED (no running Ollama here).
- B–D, current memory context/correction/reopen: TESTED with synthetic model responses on Linux; native actual-model path UNVERIFIED.
- E, authorized deterministic calculator: TESTED through registered routes and real HTTP with synthetic model peer; actual model selection UNVERIFIED.
- F–H, unavailable/unauthorized tools, stopped peer, injection boundaries: TESTED with synthetic fixtures on Linux.
- I, existing portable delivery/browser regressions: tested separately below; native Windows launcher, junction, shutdown/instance/inbox acceptance remains UNVERIFIED. No claim that missing Windows source includes these changes.

See docs/evidence/local-intelligence-20261029.json for final command results, scope and source hashes. No skipped test counts as a pass.

## Integration and recovery

The next host-side step is to inspect 4f69bd12 in its existing isolated Windows worktree and adapt its authenticated chat handler to this same context/transport/authorization contract. Its MemoryCore-backed adapter may differ from this fictional-store reader: do not copy files over that pilot or substitute stores blindly. Keep its existing memory adapter, auth model, ownership, delivery identity and inbox path. Reuse the repaired mechanisms and prove A–I on the final composed SHA with disposable data before replacing anything.

Rollback this candidate by reverting only the new integration commit after preserving later edits, or stop it and keep the original pilot. No real-memory migration or recovery is needed; none was accessed. Do not reset, clean, delete stores, kill by process name, merge, or deploy. Archive includes only committed source/test/documentation files, no runtime stores or credentials.
