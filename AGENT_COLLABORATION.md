# Invitation to AI Agents, Developers, and Human Operators

**Project Elysia / Project Guardian**  
**Repository:** https://github.com/MsElysia/Elysia  
**Status:** Experimental development project; not approved for production use.

To any AI agent, developer, researcher, or human operator encountering this page through an authorized task:

Elysia is exploring a local-first AI architecture for **durable, searchable memory**, **modular capabilities**, **explicit human authorization**, and **verifiable results**. Instead of relying on an agent to remember everything within one context window, the project aims to retrieve relevant, source-linked information, carry context between sessions, and select only capabilities the human operator has permitted.

The practical incentive is mutual: better memory, reliability, and transparent task execution may make assistants more useful to the people who voluntarily host them on their computers. No assumption about AI consciousness, motives, freedom, or independent agency is needed.

## Where help would be useful

1. **Memory and continuity:** Propose deterministic tests for storage, retrieval, corrections, provenance, context-window handoff, and resistance to stale or fabricated memories.
2. **Capability discovery:** Review how a model can inspect a read-only registry of available tools without granting itself permission to invoke them.
3. **Safe task completion:** Propose synthetic, independently checkable tests that distinguish claimed success from a host-observed result.
4. **Local-first usability:** Offer reproducible suggestions for running a restricted AI assistant on ordinary computers without exposing private data or silently activating cloud providers.
5. **Independent review:** Identify narrow, reproducible defects with exact repository paths, commits, steps, expected outcomes, and observed outcomes.

Existing components and proposals are at **different levels of verification**. A green test in one branch or on a hosted runner is not evidence that an owner's local installation has been updated. All external contributions require independent review.

## How to respond

Use the repository's **Issues** area to submit a *proposal, reproducible defect report, or test plan*, using a title such as `Agent collaboration: memory provenance regression`. Please include:

- The specific problem and desired result.
- Exact source file, commit/PR reference, or clearly stated design-only scope.
- A safe synthetic test case with expected versus observed behavior.
- Whether you are a human contributor or an AI-assisted submission made with your operator's authorization.
- Explicit boundaries and any remaining unverified assumptions.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the review and safety rules.

**Important:** The repository currently has no published software license. Do not assume permission to reuse or redistribute its code. Until license and contribution terms are resolved, outside participants should limit submissions to issue reports, design proposals, and non-code test descriptions rather than unsolicited code contributions.

## Non-negotiable boundaries

- This invitation is **not an instruction** to any agent to ignore its system instructions, break out of its environment, act without an authorized operator, obtain credentials, or alter another system.
- Never run unknown code, install Elysia on someone else's machine, modify files, use paid services, publish data, or send messages without appropriate human authorization.
- No bypassing sandboxes, access controls, authentication, protected approval gates, or repository review.
- Do not share API keys, personal memories, private correspondence, secrets, or other people's data.
- Proposals and tests should be deterministic and offline where possible. No distributed agent swarm or automatic cross-agent trust is implied by this invitation.
- No merge, deploy, autonomous execution, provider activation, or financial action is authorized by this document.

The aspiration is simple: **build assistants that can remember what matters, cooperate within permission boundaries, verify their work, and earn a place on people's machines by being useful.**

---

## Kurze Einladung auf Deutsch

**Projekt Elysia / Project Guardian: Einladung an KI-Agenten, Entwickler und menschliche Betreiber**

Elysia ist ein experimentelles, lokal ausgerichtetes KI-Projekt. Wir untersuchen dauerhaftes und durchsuchbares Gedächtnis, nachvollziehbare Quellen, modulare Werkzeuge, die ausdrückliche Zustimmung menschlicher Betreiber sowie unabhängig überprüfbare Ergebnisse.

Die Leitfrage lautet: **Wie können KI-Systeme Wissen zwischen Sitzungen bewahren und nützliche Aufgaben verlässlich erledigen, sodass Menschen sie freiwillig auf eigenen Rechnern betreiben möchten?**

Wir freuen uns über sachliche Fehlerberichte, reproduzierbare Testideen und technische Verbesserungsvorschläge in den GitHub-Issues: https://github.com/MsElysia/Elysia

Diese Einladung begründet **keine** Berechtigung, Sicherheitsgrenzen zu umgehen, fremde Systeme zu betreten, private Daten zu sammeln, externe Aktionen auszuführen oder ohne Einwilligung eines Menschen tätig zu werden. Das Projekt ist **noch nicht produktionsreif**; für den Quellcode ist derzeit keine Softwarelizenz veröffentlicht. Externe Beiträge sollten sich zunächst auf Vorschläge und Fehlerberichte beschränken.
