from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

import json
import os
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from project_guardian.auto_learning import (
    CHATLOG_REVISIT_COOLDOWN_HOURS,
    _chatlog_match_stats,
    _chatlog_revisit_allowed,
    fetch_chatlogs,
    get_chatlogs_path,
    peek_chatlogs_context,
    resolve_chatlog_search_terms,
    run_mistral_chained_learning_session,
)


class _EmptyPlanMistral:
    def __init__(self, model: str):
        self.model = model

    def suggest_learning_targets(self, context, round_index, already_tried=None, *, module_name, agent_name=None):
        return {}


def test_fetch_chatlogs_prefers_goal_matches_and_extracts_excerpt(tmp_path):
    recent = tmp_path / "recent_generic.txt"
    match = tmp_path / "goal_match.txt"

    recent.write_text("general notes\n" + ("small talk " * 120), encoding="utf-8")
    match.write_text(
        ("preface " * 900)
        + "Elysia should search set goals for automation, income, and Project Guardian.\n"
        + ("tail " * 400),
        encoding="utf-8",
    )

    now = 1_700_000_000
    os.utime(recent, (now, now))
    os.utime(match, (now - 100, now - 100))

    items = fetch_chatlogs(
        tmp_path,
        max_files=1,
        search_terms=["Elysia", "set goals", "automation"],
    )

    assert len(items) == 1
    assert items[0]["file"] == "goal_match.txt"
    assert items[0]["search_strategy"] == "goal_match"
    assert "Elysia should search set goals" in items[0]["text"]
    assert items[0]["text"].startswith("... ")
    assert "Elysia" in items[0]["matched_terms"]


def test_resolve_chatlog_search_terms_injects_language_proxies_for_code_discovery():
    terms = resolve_chatlog_search_terms([], cfg={})
    assert "python" in [t.lower() for t in terms]
    assert "typescript" in [t.lower() for t in terms]


def test_chatlog_match_stats_boosts_fenced_code_blocks():
    text = "notes\n```python\ndef foo():\n    return 2\n```\ntrailer"
    score, matched, _fp, _st = _chatlog_match_stats(text, ["python"])
    assert score >= 12
    assert "python" in matched


def test_fetch_chatlogs_reads_markdown_exports(tmp_path):
    convo = tmp_path / "export_chat.md"
    convo.write_text(
        "Operator asked about Project Guardian and Elysia.\n\n```ts\nconst x = 1;\n```\n",
        encoding="utf-8",
    )
    items = fetch_chatlogs(
        tmp_path,
        max_files=2,
        processed_path=None,
        search_terms=["elysia", "project guardian", "typescript"],
    )
    assert len(items) == 1
    assert items[0]["file"] == "export_chat.md"


def test_get_chatlogs_path_creates_local_fallback_dir(tmp_path, monkeypatch):
    local_appdata = tmp_path / "localappdata"
    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))
    real_open = open

    def _open_with_forced_fallback(*args, **kwargs):
        target = str(args[0]) if args else ""
        if target.endswith("external_storage.json"):
            raise OSError("force local fallback")
        return real_open(*args, **kwargs)

    with patch("builtins.open", side_effect=_open_with_forced_fallback):
        out = get_chatlogs_path()

    assert out == local_appdata / "ProjectGuardian" / "personal" / "chatlogs"
    assert out.exists()
    assert out.is_dir()


def test_trigger_introspection_learning_passes_chatlogs_when_enabled(tmp_path, monkeypatch):
    from project_guardian.core import GuardianCore

    learned = tmp_path / "learned"
    learned.mkdir()
    chatlogs = tmp_path / "chatlogs"
    chatlogs.mkdir()
    captured = {}

    class _Memory:
        def __init__(self) -> None:
            self.calls = []

        def remember(self, message: str, **kwargs) -> None:
            self.calls.append((message, kwargs))

    class _InlineThread:
        def __init__(self, target=None, daemon=None, name=None):
            self._target = target

        def start(self):
            if self._target is not None:
                self._target()

    def _fake_run_learning_session(**kwargs):
        captured.update(kwargs)
        return {"chatlogs": 2}

    monkeypatch.setattr("project_guardian.core.threading.Thread", _InlineThread)
    monkeypatch.setattr("project_guardian.auto_learning.get_learned_storage_path", lambda: learned)
    monkeypatch.setattr("project_guardian.auto_learning.get_chatlogs_path", lambda: chatlogs)
    monkeypatch.setattr(
        "project_guardian.auto_learning.load_learning_config",
        lambda: {
            "learning_read_chatgpt_in_introspection": True,
            "introspection_max_chatlogs": 3,
            "reddit_subs": ["LocalLLaMA"],
        },
    )
    monkeypatch.setattr("project_guardian.auto_learning.run_learning_session", _fake_run_learning_session)
    monkeypatch.setattr(
        "project_guardian.core.trigger_adversarial_on_event",
        lambda *args, **kwargs: None,
    )

    g = GuardianCore.__new__(GuardianCore)
    g.memory = _Memory()
    g._unified_system = None

    g._trigger_introspection_learning()

    assert captured["chatlogs_path"] == chatlogs
    assert captured["max_chatlogs"] == 3
    assert captured["storage_path"] == learned
    assert any("ChatGPT chatlog excerpt" in call[0] for call in g.memory.calls)


def test_resolve_chatlog_search_terms_omits_bare_internal_names_when_actionable_terms_exist():
    terms = resolve_chatlog_search_terms(
        ["automation", "income", "AI"],
        cfg={
            "chatlog_goal_terms": [
                "Elysia",
                "Project Guardian",
                "Elysia goals",
                "Project Guardian next steps",
                "set goals",
                "next steps",
                "autonomy plan",
                "service pricing",
                "customer complaint",
                "workflow fix",
                "compute credits",
                "API grants",
                "operator-ready",
            ]
        },
    )

    assert "Elysia goals" in terms
    assert "Project Guardian next steps" in terms
    assert "Elysia" not in terms
    assert "Project Guardian" not in terms


def test_fetch_chatlogs_prefers_actionable_goal_match_over_generic_elysia_mention(tmp_path):
    generic = tmp_path / "generic_elysia.txt"
    actionable = tmp_path / "actionable_goals.txt"

    generic.write_text(
        ("preface " * 100)
        + "Elysia is a fictional self-aware AI and this conversation is mostly philosophical.\n"
        + ("tail " * 60),
        encoding="utf-8",
    )
    actionable.write_text(
        ("setup " * 80)
        + "Elysia should set goals for automation, define next steps, and prioritize operator-ready services.\n"
        + ("plan " * 60),
        encoding="utf-8",
    )

    now = 1_700_000_000
    os.utime(generic, (now, now))
    os.utime(actionable, (now - 10, now - 10))

    items = fetch_chatlogs(
        tmp_path,
        max_files=1,
        search_terms=["Elysia", "goals"],
    )

    assert len(items) == 1
    assert items[0]["file"] == "actionable_goals.txt"
    assert items[0]["search_strategy"] == "goal_match"


def test_peek_chatlogs_context_labels_goal_matches(tmp_path):
    generic = tmp_path / "generic.txt"
    goal = tmp_path / "elysia_goal.txt"

    generic.write_text("general notes only\n" + ("boring " * 80), encoding="utf-8")
    goal.write_text(
        ("setup " * 120)
        + "Project Guardian should review Elysia goals and autonomy milestones.\n",
        encoding="utf-8",
    )

    now = 1_700_000_000
    os.utime(generic, (now, now))
    os.utime(goal, (now - 10, now - 10))

    context = peek_chatlogs_context(
        tmp_path,
        max_files=1,
        search_terms=["Elysia", "goals"],
    )

    assert "elysia_goal.txt" in context
    assert "matches: Elysia, goals" in context
    assert "autonomy milestones" in context


def test_fetch_chatlogs_goal_match_can_revisit_processed_file(tmp_path):
    matched = tmp_path / "elysia_goal.txt"
    generic = tmp_path / "generic.txt"
    processed = tmp_path / ".processed.json"

    matched.write_text(
        "Elysia and Project Guardian should revisit set goals and autonomy milestones.\n",
        encoding="utf-8",
    )
    generic.write_text("generic recent notes only\n", encoding="utf-8")
    processed.write_text('["elysia_goal.txt"]', encoding="utf-8")

    items = fetch_chatlogs(
        tmp_path,
        max_files=1,
        processed_path=processed,
        search_terms=["Elysia", "Project Guardian", "set goals"],
    )

    assert len(items) == 1
    assert items[0]["file"] == "elysia_goal.txt"
    assert items[0]["search_strategy"] == "goal_match_revisit"


def test_fetch_chatlogs_goal_match_revisit_respects_cooldown_metadata(tmp_path):
    matched = tmp_path / "elysia_goal.txt"
    generic = tmp_path / "generic.txt"
    processed = tmp_path / ".processed.json"

    matched.write_text(
        "Elysia and Project Guardian should revisit set goals and autonomy milestones.\n",
        encoding="utf-8",
    )
    generic.write_text("generic recent notes only\n" + ("automation " * 30), encoding="utf-8")
    processed.write_text(
        '{"elysia_goal.txt":"2099-01-01T00:00:00Z"}',
        encoding="utf-8",
    )

    items = fetch_chatlogs(
        tmp_path,
        max_files=1,
        processed_path=processed,
        search_terms=["Elysia", "Project Guardian", "set goals"],
        revisit_cooldown_hours=CHATLOG_REVISIT_COOLDOWN_HOURS,
    )

    assert len(items) == 1
    assert items[0]["file"] == "generic.txt"
    assert items[0]["search_strategy"] == "recent_backfill"


def test_fetch_chatlogs_caps_recent_backfill_when_goal_matches_are_sparse(tmp_path):
    goal = tmp_path / "goal_match.txt"
    generic_new = tmp_path / "generic_new.txt"
    generic_old = tmp_path / "generic_old.txt"

    goal.write_text(
        "Elysia should revisit automation goals and Project Guardian priorities.\n",
        encoding="utf-8",
    )
    generic_new.write_text("general notes only\n" + ("filler " * 50), encoding="utf-8")
    generic_old.write_text("older general notes\n" + ("archive " * 50), encoding="utf-8")

    now = 1_700_000_000
    os.utime(goal, (now - 100, now - 100))
    os.utime(generic_new, (now, now))
    os.utime(generic_old, (now - 50, now - 50))

    items = fetch_chatlogs(
        tmp_path,
        max_files=3,
        search_terms=["Elysia", "automation goals"],
        max_backfill_files=1,
    )

    assert [item["file"] for item in items] == ["goal_match.txt", "generic_new.txt"]
    assert items[0]["search_strategy"] == "goal_match"
    assert items[1]["search_strategy"] == "recent_backfill"


def test_fetch_chatlogs_caps_goal_match_revisits_in_chained_mode(tmp_path):
    revisit_a = tmp_path / "goal_revisit_a.txt"
    revisit_b = tmp_path / "goal_revisit_b.txt"
    generic = tmp_path / "generic.txt"
    processed = tmp_path / ".processed.json"

    revisit_a.write_text(
        "Elysia should revisit automation goals and operator-ready autonomy plans.\n" + ("details " * 20),
        encoding="utf-8",
    )
    revisit_b.write_text(
        "Project Guardian autonomy goals need another revisit for income and automation planning.\n" + ("notes " * 20),
        encoding="utf-8",
    )
    generic.write_text("general notes only\n" + ("filler " * 40), encoding="utf-8")
    processed.write_text(
        json.dumps(
            {
                "goal_revisit_a.txt": "2020-01-01T00:00:00Z",
                "goal_revisit_b.txt": "2020-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    now = 1_700_000_000
    os.utime(revisit_a, (now, now))
    os.utime(revisit_b, (now - 10, now - 10))
    os.utime(generic, (now - 20, now - 20))

    items = fetch_chatlogs(
        tmp_path,
        max_files=3,
        processed_path=processed,
        search_terms=["Elysia", "goals", "Project Guardian"],
        max_revisit_files=1,
        max_backfill_files=1,
    )

    assert len(items) == 2
    assert items[0]["search_strategy"] == "goal_match_revisit"
    assert items[1]["search_strategy"] == "recent_backfill"


def test_fetch_chatlogs_can_use_local_mistral_rerank_for_close_candidates(tmp_path):
    generic = tmp_path / "generic_elysia.txt"
    actionable = tmp_path / "actionable_operator.txt"

    generic.write_text(
        ("Elysia goals and Elysia goals are discussed here. " * 12)
        + "Elysia is a fictional self-aware AI and this is mostly philosophical.",
        encoding="utf-8",
    )
    actionable.write_text(
        ("Elysia goals appear once here. " * 4)
        + "Need to set goals, define next steps, fix the workflow, and ship an operator-ready service.",
        encoding="utf-8",
    )

    class _FakeReranker:
        def complete_chat(self, *args, **kwargs):
            return json.dumps(
                {
                    "rankings": [
                        {
                            "file": "actionable_operator.txt",
                            "actionable": True,
                            "priority": 5,
                            "category": "operational",
                            "reason": "Contains concrete next steps and shipping work.",
                        },
                        {
                            "file": "generic_elysia.txt",
                            "actionable": False,
                            "priority": 0,
                            "category": "generic",
                            "reason": "Mostly identity and philosophy chatter.",
                        },
                    ]
                }
            )

    items = fetch_chatlogs(
        tmp_path,
        max_files=1,
        search_terms=["Elysia", "goals"],
        llm_reranker=_FakeReranker(),
        llm_rerank_top_n=2,
    )

    assert len(items) == 1
    assert items[0]["file"] == "actionable_operator.txt"


def test_chained_learning_uses_resolved_goal_terms_for_chatlogs(tmp_path):
    captured = {"fetch": None, "peek": None}

    def _fake_fetch_chatlogs(
        _path,
        max_files=20,
        processed_path=None,
        search_terms=None,
        revisit_cooldown_hours=None,
        max_backfill_files=None,
        max_revisit_files=None,
        llm_reranker=None,
        llm_rerank_top_n=0,
    ):
        captured["fetch"] = {
            "terms": list(search_terms or []),
            "max_files": max_files,
            "max_backfill_files": max_backfill_files,
            "max_revisit_files": max_revisit_files,
            "llm_reranker": llm_reranker,
            "llm_rerank_top_n": llm_rerank_top_n,
        }
        return []

    def _fake_peek_chatlogs_context(_path, max_files=5, max_chars_per_file=2500, search_terms=None, max_backfill_files=None, max_revisit_files=None):
        captured["peek"] = {
            "terms": list(search_terms or []),
            "max_files": max_files,
            "max_backfill_files": max_backfill_files,
            "max_revisit_files": max_revisit_files,
        }
        return ""

    with (
        patch("project_guardian.mistral_engine.MistralEngine", _EmptyPlanMistral),
        patch("project_guardian.ollama_model_config.get_canonical_ollama_model", return_value="mistral:7b"),
        patch("project_guardian.planner_readiness.should_short_circuit_verify_ollama_for_bad_tag", return_value=(False, "")),
        patch(
            "project_guardian.auto_learning.load_learning_config",
            return_value={
                "enable_moltbook_auto_learn": False,
                "max_chatlogs": 15,
                "mistral_chained_max_chatlogs": 4,
                "mistral_chained_chatlog_backfill_cap": 2,
                "mistral_chained_chatlog_revisit_cap": 3,
                "mistral_chained_chatlog_llm_rerank_top_n": 4,
                "mistral_chained_max_rounds": 1,
                "mistral_chained_per_source_cap": 1,
                "chatlog_goal_terms": ["set goals", "income"],
            },
        ),
        patch("project_guardian.auto_learning.fetch_chatlogs", side_effect=_fake_fetch_chatlogs),
        patch("project_guardian.auto_learning.peek_chatlogs_context", side_effect=_fake_peek_chatlogs_context),
        patch("project_guardian.auto_learning.fetch_reddit", return_value=[]),
        patch("project_guardian.auto_learning.fetch_wikipedia_summary", return_value=None),
        patch("project_guardian.auto_learning.fetch_twitter", return_value=[]),
        patch("project_guardian.auto_learning.compress_with_llm", side_effect=lambda text, cb, *, module_name, agent_name=None: text),
        patch(
            "project_guardian.auto_learning.finalize_learned_collection",
            return_value={
                "fetched": 0,
                "archived": 0,
                "admitted": 0,
                "rejected": 0,
                "cross_session_duplicates": 0,
                "file": "",
                "memory_count": 0,
            },
        ),
    ):
        run_mistral_chained_learning_session(
            storage_path=tmp_path,
            topics=["automation"],
            memory=None,
            llm_callback=None,
            chatlogs_path=tmp_path,
            twitter_bearer_token=None,
            default_reddit_subs=["MachineLearning"],
        )

    expected = resolve_chatlog_search_terms(
        ["automation"],
        cfg={"chatlog_goal_terms": ["set goals", "income"]},
    )
    assert captured["fetch"]["terms"] == expected
    assert captured["peek"]["terms"] == expected
    assert captured["fetch"]["max_files"] == 4
    assert captured["peek"]["max_files"] == 3
    assert captured["fetch"]["max_backfill_files"] == 2
    assert captured["peek"]["max_backfill_files"] == 1
    assert captured["fetch"]["max_revisit_files"] == 3
    assert captured["peek"]["max_revisit_files"] == 2
    assert captured["fetch"]["llm_rerank_top_n"] == 4
    assert captured["fetch"]["llm_reranker"] is not None


def test_chained_learning_disables_chatlog_rerank_in_startup_thin_mode(tmp_path):
    captured = {"fetch": None}

    def _fake_fetch_chatlogs(
        _path,
        max_files=20,
        processed_path=None,
        search_terms=None,
        revisit_cooldown_hours=None,
        max_backfill_files=None,
        max_revisit_files=None,
        llm_reranker=None,
        llm_rerank_top_n=0,
    ):
        captured["fetch"] = {
            "llm_reranker": llm_reranker,
            "llm_rerank_top_n": llm_rerank_top_n,
        }
        return []

    with (
        patch("project_guardian.mistral_engine.MistralEngine", _EmptyPlanMistral),
        patch("project_guardian.ollama_model_config.get_canonical_ollama_model", return_value="mistral:7b"),
        patch("project_guardian.planner_readiness.should_short_circuit_verify_ollama_for_bad_tag", return_value=(False, "")),
        patch(
            "project_guardian.auto_learning.load_learning_config",
            return_value={
                "enable_moltbook_auto_learn": False,
                "mistral_chained_max_chatlogs": 4,
                "mistral_chained_chatlog_llm_rerank_top_n": 4,
                "mistral_chained_max_rounds": 1,
                "mistral_chained_per_source_cap": 1,
            },
        ),
        patch("project_guardian.auto_learning.fetch_chatlogs", side_effect=_fake_fetch_chatlogs),
        patch("project_guardian.auto_learning.peek_chatlogs_context", return_value=""),
        patch("project_guardian.auto_learning.fetch_reddit", return_value=[]),
        patch("project_guardian.auto_learning.fetch_wikipedia_summary", return_value=None),
        patch("project_guardian.auto_learning.fetch_twitter", return_value=[]),
        patch("project_guardian.auto_learning.compress_with_llm", side_effect=lambda text, cb, *, module_name, agent_name=None: text),
        patch(
            "project_guardian.auto_learning.finalize_learned_collection",
            return_value={
                "fetched": 0,
                "archived": 0,
                "admitted": 0,
                "rejected": 0,
                "cross_session_duplicates": 0,
                "file": "",
                "memory_count": 0,
            },
        ),
    ):
        run_mistral_chained_learning_session(
            storage_path=tmp_path,
            topics=["automation"],
            memory=None,
            llm_callback=None,
            chatlogs_path=tmp_path,
            twitter_bearer_token=None,
            default_reddit_subs=["MachineLearning"],
            disable_chatlog_rerank=True,
        )

    assert captured["fetch"] is not None
    assert captured["fetch"]["llm_rerank_top_n"] == 0
    assert captured["fetch"]["llm_reranker"] is None


def test_chatlog_revisit_same_day_requires_long_gap():
    fixed = datetime(2026, 4, 20, 18, 0, 0, tzinfo=timezone.utc)
    with patch("project_guardian.auto_learning._utc_now", return_value=fixed):
        recent = (fixed - timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert _chatlog_revisit_allowed(recent, cooldown_hours=1.0) is False
        old = (fixed - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert _chatlog_revisit_allowed(old, cooldown_hours=1.0) is True
