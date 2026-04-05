# Adversarial Self-Learning: Trace and Refactor Summary

## 1. Where it is initialized (before and after)

### Before (Legacy - TrustMatrix-adversarial)
- **File:** `project_guardian/trust.py`
- **Function:** `TrustMatrix.__init__`
- **Lines:** 101–118
- **Object:** `self.adversarial_system` (AdversarialAISelfImprovement from extracted_modules)
- **Note:** Only if `extracted_modules/adversarial_ai_self_improvement.py` exists. Otherwise `None`.

### After (New – Central Orchestrator)
- **File:** `project_guardian/adversarial_self_learning.py`
- **Functions:** `run_adversarial_cycle(guardian)`, `get_adversarial_status(guardian)`
- **Initialization:** No explicit init; invoked on demand. First run typically ~15s after startup via SystemMonitor.

---

## 2. Where it is invoked now

| Location | File | Trigger |
|----------|------|---------|
| Post-startup | `monitoring.py` ~453 | ~15s after monitoring start, after first autonomy cycle |
| Autonomy loop | `core.py` run_autonomous_cycle | When `consider_adversarial_learning` is selected by get_next_action |
| get_next_action | `core.py` | Candidate every 30 min (throttled by `_adversarial_last_run`) |

---

## 3. What currently consumes its outputs

| Output | Consumer | Behavioral effect |
|--------|----------|-------------------|
| Memory entries | `memory.remember(..., category="adversarial_finding")` | Persistent findings; searchable for future decisions |
| Tasks | `tasks.create_task(..., category="adversarial")` | High-priority findings become follow-up tasks for Architect/planner |
| Status | `get_system_status()["adversarial_self_learning"]` | Visibility: last_run, findings_count, top_weakness, tasks_created |
| Logs | `logger.info(...)` | Operational visibility |

---

## 4. Exact gap that prevented it from being central (before)

1. **Never invoked:** `TrustMatrix.run_adversarial_improvement_cycle()` had no callers.
2. **Synthetic-only:** `AdversarialAISelfImprovement` ran trust-decay debates, not analysis of real Guardian data.
3. **No real inputs:** No access to failures, learning, cleanup, task outcomes.
4. **No behavioral outputs:** Trust delta only; no tasks, prompts, or memory entries driving behavior.
5. **Disconnected from planner:** Not in get_next_action or autonomy cycle; planner never used it.
6. **Optional module:** Depends on extracted_modules; easily disabled or missing.

---

## 5. Refactor plan implemented

1. **New orchestrator:** `project_guardian/adversarial_self_learning.py` with `run_adversarial_cycle()`.
2. **Real inputs:** Recent memories (errors, learning, monitoring), active tasks.
3. **Heuristic analysis:** Repeated failures, cleanup anomalies, low-signal learning, task outcomes.
4. **Structured outputs:** Findings with type, priority, suggested_action; written to memory and tasks.
5. **Autonomy integration:** `consider_adversarial_learning` added to get_next_action and run_autonomous_cycle.
6. **Triggers:** Post-startup (15s), autonomy selection (throttled 30 min).
7. **Visibility:** `adversarial_self_learning` status in `get_system_status()`.
8. **Config:** `consider_adversarial_learning` in autonomy.json allowed_actions.

---

## 6. Behavioral paths that now depend on it

| Path | Dependence |
|------|-------------|
| Autonomy decision loop | get_next_action suggests consider_adversarial_learning |
| Task creation | High-priority findings create tasks (category=adversarial) |
| Memory | Findings stored as adversarial_finding; feed future introspection/decisions |
| System status / UI | Status shows last run, findings count, top weakness |
| Post-startup | First run ~15s after monitoring start |

---

## 7. Example logs showing it driving future behavior

```
[SystemMonitor] Post-startup adversarial self-learning completed
[Adversarial Self-Learning] Run complete: findings=2 top=Repeated failure (3x): [Error]... tasks_created=1 memory_writes=2
[Autonomy] Executed consider_adversarial_learning: findings=2 tasks=1
[Guardian Task] Created: Adversarial: investigate_repeated_failure - Repeated failure (3x): ...
```

The tasks created (e.g. `execute_task` for adversarial tasks) are then picked up by get_next_action in future cycles, so Architect/planner can act on them.

---

## Appendix: Prioritization rules (adversarial_self_learning.py)

| Signal | Finding type | Priority | Suggested action |
|--------|--------------|----------|------------------|
| 2+ identical/similar errors | weakness | 0.6 + 0.1×count (cap 0.9) | investigate_repeated_failure |
| 3+ cleanup skips | anomaly | 0.7 | review_cleanup_threshold |
| 50%+ low-priority learning | improvement_proposal | 0.65 | review_learning_admission |
| 3+ failed/cancelled tasks | weakness | 0.75 | review_task_queue |

---

## Appendix: Explicit inputs analyzed

- Recent memories (limit 100, any category)
- Learning memories (category=learning, limit 30)
- Active tasks (from TaskEngine.get_active_tasks)

---

## Appendix: Explicit outputs produced

- **Memory:** `category="adversarial_finding"`, metadata: finding_type, suggested_action, detail
- **Tasks:** For findings with priority ≥ 0.75, `create_task(..., category="adversarial")`
- **Status:** `guardian._adversarial_last_run` and `get_adversarial_status()` for visibility
