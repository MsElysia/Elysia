from project_guardian.prompt_evolution import (
    generate_prompt_candidates,
    promote_prompt_candidate,
    rollback_prompt,
    run_prompt_health_check,
    test_prompt_candidate,
)


def test_candidate_schema_preservation():
    base = {"prompt_id": "memory.condensation.v1", "version": 1, "output_schema": {"required": ["a"]}, "behavioral_instructions": []}
    reviews = [{"recommended_changes": ["be strict on json"]}]
    cands = generate_prompt_candidates(base, reviews, max_candidates=1)
    assert cands
    assert cands[0]["output_schema"] == base["output_schema"]


def test_candidate_regression_detection_shape():
    score = test_prompt_candidate({"prompt_id": "x"}, [{"task_id": "a", "task": {"x": 1}}, {"task_id": "b"}], [])
    assert "score" in score and "details" in score


def test_promotion_and_rollback_roundtrip():
    p = promote_prompt_candidate("memory.condensation.v1", "memory.condensation.v2")
    assert p["promoted"] is True
    rb = rollback_prompt("memory.condensation.v1", 1)
    assert rb["rolled_back"] is True


def test_auto_promote_false_behavior():
    hc = run_prompt_health_check()
    assert hc["auto_promote_enabled"] is False
