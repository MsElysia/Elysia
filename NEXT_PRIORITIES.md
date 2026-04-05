# Next Priorities for Elysia

Based on ChatGPT's strategic analysis, here are the recommended next steps:

## 🎯 Priority #1: Implementer Agent (CRITICAL)

**Why:** Without execution, Elysia is just a proposal engine, not a self-improving system.

**What it needs to do:**
1. Monitor approved proposals
2. Create code branches
3. Generate implementation plans
4. Write code
5. Run tests
6. Submit patches (Cursor PRs)
7. Request human review when stuck

**Status:** Not started
**Impact:** HIGH - This is the missing execution layer

---

## 🎯 Priority #2: Auto-Scoring System

**Why:** Current scoring is manual/fake. Need evidence-driven, validated scoring.

**What it needs:**
- Evidence-driven calculation
- Domain-informed scoring
- Consistent across proposals
- Explainable results
- Validated against history

**Status:** Fields exist, but not automated
**Impact:** HIGH - Governance system is cosmetic without this

---

## 🎯 Priority #3: WebScout Real Research Mode

**Why:** Currently using shallow LLM summaries. Need real web research capability.

**What it needs:**
- Browser automation
- Scraping
- Citation extraction
- Page classification
- Summarization
- Fact scoring
- Cross-source verification

**Status:** Basic LLM research working, but shallow
**Impact:** MEDIUM-HIGH - Proposal quality depends on this

---

## 🎯 Priority #4: Tighten Governance

**Why:** Need stricter controls and auditing.

**What it needs:**
- Proposal rejection reasons tracking
- WebScout behavior auditing
- Automated domain mismatch detection
- Source reliability scoring
- Proposal complexity estimation

**Status:** Partially implemented
**Impact:** MEDIUM - Improves system reliability

---

## 🎯 Priority #5: Autonomy Loop

**Why:** Elysia should act autonomously, not just when prompted.

**What it needs:**
- Scheduler
- Cadence/rhythm
- Event triggers
- Goal recursion
- Work queues
- Feedback loop

**Status:** Not started
**Impact:** HIGH - Makes Elysia truly autonomous

---

## Recommendation

**Start with Priority #1: Implementer Agent**

This is the critical missing piece. Everything else builds on having execution capability.

---

**Decision Point:** Which priority should we tackle first?

