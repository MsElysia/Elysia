from pathlib import Path

from elysia.agents.implementer import ImplementerAgent
from elysia.agents.webscout import WebScoutAgent
from elysia.core.proposal_system import ProposalSystem
from elysia.events import EventBus
from project_guardian.webscout_agent import ResearchSource


def _proposal_system(tmp_path: Path, event_bus: EventBus) -> ProposalSystem:
    return ProposalSystem(tmp_path / "proposals", event_bus=event_bus, enable_watcher=False)


def test_create_proposal_returns_real_proposal_id(tmp_path, monkeypatch):
    monkeypatch.setenv("ELYSIA_WEBSCOUT_SKIP_GUARDIAN_READER", "1")
    event_bus = EventBus()
    proposal_system = _proposal_system(tmp_path, event_bus)
    agent = WebScoutAgent(
        proposal_system.proposals_root,
        proposal_system,
        event_bus=event_bus,
        repo_root=tmp_path,
    )

    proposal_id = agent.create_proposal(
        "Improve proposal flow",
        "Make WebScout create real proposal artifacts.",
        check_duplicates=False,
    )

    assert proposal_id
    proposal = proposal_system.get_proposal(proposal_id)
    assert proposal is not None
    assert proposal["status"] == "research"
    assert proposal["domain"] == "elysia_core"
    assert (proposal_system.proposals_root / proposal_id / "metadata.json").is_file()

    events = event_bus.get_recent_events()
    assert any(evt["type"] == "proposal_created" and evt["payload"]["proposal_id"] == proposal_id for evt in events)


def test_research_topic_creates_complete_proposal_package(tmp_path, monkeypatch):
    monkeypatch.setenv("ELYSIA_WEBSCOUT_SKIP_GUARDIAN_READER", "1")
    event_bus = EventBus()
    proposal_system = _proposal_system(tmp_path, event_bus)
    agent = WebScoutAgent(
        proposal_system.proposals_root,
        proposal_system,
        event_bus=event_bus,
        repo_root=tmp_path,
    )

    def fake_research(query: str, max_sources: int = 5):
        assert query == "Better internal task graph orchestration"
        assert max_sources == 2
        return (
            [
                ResearchSource(
                    url="https://example.com/task-graphs",
                    title="Task Graph Patterns",
                    relevance="high",
                    extracted_patterns=[
                        "Use explicit lifecycle states for queued, running, and completed tasks",
                        "Persist edge metadata so retries can resume safely",
                    ],
                    summary="Task graph systems benefit from durable state and small execution units.",
                )
            ],
            "Durable task graphs need lifecycle state, retry metadata, and small execution units.",
        )

    agent._webscout_instance.conduct_web_research = fake_research

    result = agent.research_topic(
        "Better internal task graph orchestration",
        max_sources=2,
        check_duplicates=False,
    )

    proposal_id = result["proposal_id"]
    proposal_path = proposal_system.proposals_root / proposal_id

    assert result["status"] == "proposal"
    assert result["implementation_plan_source"] == "generated"
    assert result["source_count"] == 1
    assert proposal_system.get_proposal(proposal_id)["status"] == "proposal"
    assert (proposal_path / "research" / "summary.md").is_file()
    assert (proposal_path / "research" / "sources.md").is_file()
    assert (proposal_path / "design" / "architecture.md").is_file()
    assert (proposal_path / "design" / "integration.md").is_file()
    assert (proposal_path / "design" / "implementation_plan.md").is_file()
    assert (proposal_path / "implementation" / "todos.md").is_file()
    assert (proposal_path / "implementation" / "tests.md").is_file()

    architecture = (proposal_path / "design" / "architecture.md").read_text(encoding="utf-8")
    todos = (proposal_path / "implementation" / "todos.md").read_text(encoding="utf-8")
    implementation_plan = (proposal_path / "design" / "implementation_plan.md").read_text(encoding="utf-8")

    assert "Use explicit lifecycle states" in architecture
    assert "placeholder architecture" not in architecture.lower()
    assert "Review research findings" in todos
    assert "Create file proposals/" in implementation_plan
    assert "implementation/generated_plan.md" in implementation_plan
    assert "Generated Implementation Brief" in implementation_plan

    events = event_bus.get_recent_events()
    assert any(evt["type"] == "research_completed" and evt["payload"]["proposal_id"] == proposal_id for evt in events)


def test_research_topic_can_write_explicit_implementation_plan(tmp_path, monkeypatch):
    monkeypatch.setenv("ELYSIA_WEBSCOUT_SKIP_GUARDIAN_READER", "1")
    event_bus = EventBus()
    proposal_system = _proposal_system(tmp_path, event_bus)
    agent = WebScoutAgent(
        proposal_system.proposals_root,
        proposal_system,
        event_bus=event_bus,
        repo_root=tmp_path,
    )

    def fake_research(query: str, max_sources: int = 5):
        return (
            [
                ResearchSource(
                    url="https://example.com/patchable",
                    title="Patchable Plans",
                    relevance="high",
                    extracted_patterns=["Use explicit file targets with replacement content"],
                    summary="Implementation plans should identify target files.",
                )
            ],
            "Patchable implementation plans need explicit file paths and replacement content.",
        )

    agent._webscout_instance.conduct_web_research = fake_research
    implementation_plan = """## Step 1: Modify file src/example.py

Replace the file with the approved implementation.

```python
VALUE = 2
```
"""

    result = agent.research_topic(
        "Patchable proposal plan",
        check_duplicates=False,
        implementation_plan=implementation_plan,
    )

    plan_path = Path(result["artifacts"]["implementation_plan"])

    assert result["implementation_plan_source"] == "provided"
    assert plan_path.is_file()
    assert plan_path.read_text(encoding="utf-8") == implementation_plan.strip() + "\n"

    events = event_bus.get_recent_events()
    assert any(
        evt["type"] == "implementation_plan_written"
        and evt["payload"]["proposal_id"] == result["proposal_id"]
        for evt in events
    )


def test_generated_implementation_plan_can_be_approved_and_applied(tmp_path, monkeypatch):
    monkeypatch.setenv("ELYSIA_WEBSCOUT_SKIP_GUARDIAN_READER", "1")
    event_bus = EventBus()
    proposal_system = _proposal_system(tmp_path, event_bus)
    agent = WebScoutAgent(
        proposal_system.proposals_root,
        proposal_system,
        event_bus=event_bus,
        repo_root=tmp_path,
    )

    def fake_research(query: str, max_sources: int = 5):
        return (
            [
                ResearchSource(
                    url="https://example.com/safe-generated-plan",
                    title="Safe Generated Plans",
                    relevance="high",
                    extracted_patterns=["Keep generated implementation artifacts proposal-local"],
                    summary="Generated patch plans should avoid source edits until exact replacements are known.",
                )
            ],
            "Generated patch plans should create reviewable artifacts before touching source files.",
        )

    agent._webscout_instance.conduct_web_research = fake_research

    result = agent.research_topic(
        "Safe generated implementation plan",
        check_duplicates=False,
    )
    proposal_id = result["proposal_id"]

    success, error = proposal_system.approve_proposal(proposal_id, "tester")
    assert success, error

    implementer = ImplementerAgent(
        repo_root=tmp_path,
        proposal_system=proposal_system,
        event_bus=event_bus,
        dry_run=False,
    )
    implementation = implementer.run_for_proposal(proposal_id)

    generated_brief = proposal_system.proposals_root / proposal_id / "implementation" / "generated_plan.md"
    assert implementation["success"] is True
    assert implementation["steps_completed"] == 1
    assert generated_brief.is_file()
    assert "Safe generated implementation plan" in generated_brief.read_text(encoding="utf-8")
    proposal = proposal_system.get_proposal(proposal_id)
    assert proposal["status"] == "implemented"
    assert proposal["implementation_status"] == "completed"
