from elysia_collective_seed.autopilot.dispatcher import Worker
from elysia_collective_seed.autopilot.verifier import select_verifier


def worker(worker_id: str, group: str, *, quality: float = 0.5) -> tuple[Worker, str]:
    return (
        Worker(
            worker_id=worker_id,
            provider="test",
            capabilities=frozenset({"verification"}),
            risk_classes=frozenset({"repo_write"}),
            quality=quality,
        ),
        group,
    )


def test_producer_cannot_verify_own_write():
    producer, group = worker("producer", "group-a")
    decision = select_verifier(
        producer_worker_id="producer",
        producer_independence_group=group,
        workers=[producer],
        independence_groups={"producer": group},
    )
    assert decision.state == "blocked"
    assert decision.worker_id is None
    assert decision.reasons == ("no_independent_verifier",)


def test_same_independence_group_is_rejected():
    producer, group = worker("producer", "group-a")
    peer, _ = worker("peer", "group-a")
    decision = select_verifier(
        producer_worker_id="producer",
        producer_independence_group=group,
        workers=[producer, peer],
        independence_groups={"producer": group, "peer": group},
    )
    assert decision.state == "blocked"


def test_distinct_group_can_claim_verification():
    producer, group = worker("producer", "group-a")
    verifier, verifier_group = worker("verifier", "group-b", quality=0.9)
    decision = select_verifier(
        producer_worker_id="producer",
        producer_independence_group=group,
        workers=[producer, verifier],
        independence_groups={"producer": group, "verifier": verifier_group},
    )
    assert decision.state == "verification_claim"
    assert decision.worker_id == "verifier"


def test_missing_group_metadata_fails_closed():
    producer, group = worker("producer", "group-a")
    verifier, _ = worker("verifier", "group-b")
    decision = select_verifier(
        producer_worker_id="producer",
        producer_independence_group=group,
        workers=[producer, verifier],
        independence_groups={"producer": group},
    )
    assert decision.state == "blocked"


def test_spoofed_producer_group_fails_closed():
    producer, _ = worker("producer", "real-group")
    verifier, _ = worker("verifier", "real-group")
    decision = select_verifier(
        producer_worker_id="producer",
        producer_independence_group="spoofed-group",
        workers=[producer, verifier],
        independence_groups={"producer": "real-group", "verifier": "real-group"},
    )
    assert decision.state == "blocked"
    assert decision.reasons == ("producer_independence_metadata_invalid",)
