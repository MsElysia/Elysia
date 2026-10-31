# Existing restricted browser + verified calculator

Base: PR175 `452d986fae4c98bbf3e6c6910584c7ab1a1a8a7c`. Selective browser/runtime closure source: PR168 `4eea564b0de97c124aea7475527e7ab542249ffc`. No PR172 adoption or divergent history merge.

## Existing interface, stronger admission

Run `python -B elysia_restricted_browser.py --port 5077 --store <new-synthetic-name>` in an isolated checkout. The original terminal prompt chooses a temporary password; the original loopback-only server, exact Host/Origin/CSRF/session checks, HttpOnly/SameSite cookie, request size/method/query restrictions, CSP and no external assets remain.

The same page now offers a precise labor-input review. Prepare creates only PR175's frozen session-owned request, not an authority grant or successful task. The server binds that pending object to the authenticated browser session for120seconds. The operator reviews the rate/quantities, types the host-provided request-specific AUTHORIZE phrase, and re-enters the same existing session password. Confirmation accepts only request_id, phrase and password, never inputs, paths or grants.

The browser reuses the original scrypt password verifier and failure budget, then calls PR175 authorize/execute. Grants remain opaque/server-side, expire at the earliest of the existing120seconds, review deadline and browser-session expiry, and are consumed once. Login/logout revocation serializes with dispatch through the existing operation gate. Pending review is invalidated on replacement, confirmation attempt, logout/relogin, expiry and successful memory changes. No checkbox, model response, JSON authorization flag or advertisement grants execution authority.

The calculator, independent integer-cent check, primary MemoryCore audit, queue/objective/value projections and restart behavior are PR175's existing implementation. Its only adaptations are fresh read_outcomes and a tighter optional grant deadline/exclusive expiry check. Status retrieval reloads committed evidence without invoking a capability. The page distinguishes verified computation, audit persistence and the absence of external/durable capability effects.

## Keep memory and model paths

Existing guarded memory workers still teach, correct, retrieve current facts and preserve revision history. They run in their original isolated synthetic memory workspace with the same recursive snapshot/transaction guard. PR175's single task journal uses a fixed sibling directory, `.synthetic-pilot-task-journals/browser-<store>/verified-calculations-v1`. This is the existing task journal/backend, not a replacement or copy of the learning memory store. Nesting its Windows byte-lock file under the memory snapshot was independently shown incompatible, so that worker boundary was preserved.

The existing local-model path may propose a labor calculation from validated current source bytes. Its old checkbox now permits proposals only. Direct model-selected arithmetic was removed. The same review form handles a proposal; source identity/hash/revision is rechecked before dispatch and memory correction invalidates pending reviews. Only deterministic synthetic model responses are tested; no local/cloud model is activated. Calculation audit records retain confirmed inputs; ephemeral proposal source review is not a new durable memory subsystem.

## Provenance and compatibility

PR163 `9bd56b9481a12ae52fd510ece2789c6cf02134db`, PR164 `c95726054dc36de9e1488165249c6a777b0462c3`, PR165 `e3f95a8906d04cfe5562bc3aa56d3dd83b326d1b`, PR166 `d00adae5d96be78afb658f2d3584429f4e696d76`, PR167 `d2551bc493642a8e05238f135bba4471923817ff`, PR168 `4eea564b0de97c124aea7475527e7ab542249ffc` were inspected. Each prior numbered head is an ancestor of the next despite intervening commits; PR175 is a distinct lineage. Exact source blobs/adaptations are listed in browser-calculator-v1.json.

Only the minimal already-existing browser/guarded-memory closure is imported. Existing auto_learning.py and ToolRegistry are identical and are not replaced. The source lazy package initializer preserves existing public exports while preventing a restricted -S worker from importing legacy core/providers. A fresh-process regression checks both absence of implicit core load and explicit public export compatibility. Original startup launchers, Windows pilot, DigitalSafehouse and other historical modules are not imported or modified.

## Verification

The focused Windows/Linux workflow asserts event HEAD, fetches the pinned calculator source, and runs the existing17574-case suite plus the imported100browser/context/memory cases and36new browser integration cases. The original bridge tests install a process-global network-denial audit hook; these cases use real Flask registered routes and actual guarded subprocess memory workers, not a listener. Browser UI demonstration is performed separately on an owned loopback fixture so the deny hook is not weakened.

New negative cases cover authentication/Host/Origin/CSRF denial, malformed/tampered confirmation, different inputs/unknown identities, same-password reauthentication throttling, replay/expiry/logout/relogin, model/checkbox false authority, stale source, unrelated writes, interrupted calculation, failed attempted and terminal commits, concurrent browser sessions, competing app ownership, revocation races and equality-at-dispatch expiry. Real browser demonstration confirms the visible result and status reload after server restart. Existing175 tests additionally cover actual process death and fresh-process recovery. Platform-specific inherited source skips are reported precisely; no new calculator/browser integration case may skip.

Independent review found and closed the logout race and exact-expiry boundary. Final exact-head independent replay and hosted evidence are required and recorded separately in delivery artifacts. No READY_FOR_MERGE_REVIEW or release readiness claim follows from synthetic tests.

## Rollback / boundaries / next

Abandon this additive child draft, or revert only its child commit(s) if separately imported. PR175 and all source refs remain intact. Retain synthetic journals for evidence; never copy them into operational memory or clear persistence fences manually.

The operator browser/session and OS-owned journal are trusted. No cryptographic protection against a hostile OS account rewriting all state is claimed. The working Windows pilot is untouched; no personal memory, actual credentials, provider/autonomy activation, merge or deployment occurs. A live Ollama/browser-to-real-model acceptance run remains separate and unverified.

Next smallest unlock: independently verify a real, explicitly configured local Ollama proposal through the same review/confirmation flow, using only disposable synthetic sources and preserving the current-source correction fence.
