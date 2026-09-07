from elysia_collective_seed.autopilot.dispatcher import Worker, dispatch, validate_followup


def workers():
    return [
        Worker("codex", "openai", frozenset({"implementation", "test"}), frozenset({"sandbox_write", "repo_write"}), quality=.9, cost=.6),
        Worker("cursor-local", "cursor", frozenset({"archaeology", "analysis"}), frozenset({"read_only", "sandbox_write"}), quality=.8, cost=.4),
    ]


def task(**overrides):
    base = {
        "task_id": "ELY-TASK-000001",
        "title": "Implement bounded adapter",
        "status": "queued",
        "task_class": "implementation",
        "risk_class": "repo_write",
        "dependencies": [],
        "acceptance_criteria": ["tests pass"],
        "source_refs": ["github:#8"],
        "attempt": 0,
        "max_attempts": 3,
    }
    base.update(overrides)
    return base


def test_routes_to_capable_worker():
    d = dispatch(task(), {}, workers())
    assert d.state == "dispatch"
    assert d.worker_id == "codex"


def test_blocks_incomplete_dependency():
    d = dispatch(task(dependencies=["ELY-TASK-000000"]), {"ELY-TASK-000000": "running"}, workers())
    assert d.state == "blocked"
    assert "dependencies_incomplete" in d.reasons


def test_protected_risk_requires_gate():
    d = dispatch(task(risk_class="deployment"), {}, workers())
    assert d.state == "human_gate"


def test_attempt_limit_blocks_retry():
    d = dispatch(task(attempt=3, max_attempts=3), {}, workers())
    assert d.state == "blocked"
    assert "attempt_limit_reached" in d.reasons


def test_followup_cannot_expand_source_scope():
    parent = task()
    proposal = task(task_id="ELY-TASK-000002", title="Follow up", risk_class="sandbox_write", source_refs=["github:#8", "private:new"])
    ok, reasons = validate_followup(parent, proposal, [])
    assert not ok
    assert "source_scope_expansion" in reasons


def test_followup_deduplicates_title():
    parent = task()
    proposal = task(task_id="ELY-TASK-000002", title="Follow up", risk_class="sandbox_write")
    open_tasks = [{"title": " follow UP "}]
    ok, reasons = validate_followup(parent, proposal, open_tasks)
    assert not ok
    assert "duplicate_open_task" in reasons


def test_bounded_followup_is_accepted():
    parent = task()
    proposal = task(task_id="ELY-TASK-000002", title="Add more tests", risk_class="sandbox_write")
    ok, reasons = validate_followup(parent, proposal, [])
    assert ok
    assert reasons == ()
