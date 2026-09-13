from elysia_collective_seed.dry_run_harness import (
    Packet,
    make_packet,
    route,
    run_ec001_dry_run,
    validate_trace,
)


def test_ec001_trace_is_valid():
    trace = run_ec001_dry_run()
    validate_trace(trace)
    assert len(trace) == 6
    assert trace[-1].author == "Elysia"
    assert trace[-1].type == "synthesis"
    assert trace[-1].status == "supported"


def test_routing_is_need_driven_and_unique():
    packet = make_packet(
        99,
        type="hypothesis",
        author="Explorer",
        claim="Test routing",
        confidence=0.5,
        needs=["research", "critique", "research"],
    )
    assert route(packet) == ["Researcher", "Erebus"]


def test_forward_parent_is_rejected():
    bad = Packet(
        packet_id="ELY-000001",
        type="hypothesis",
        author="Explorer",
        claim="Bad lineage",
        confidence=0.5,
        status="open",
        parents=["ELY-000002"],
    )
    try:
        validate_trace([bad])
    except ValueError as exc:
        assert "missing or forward parent" in str(exc)
    else:
        raise AssertionError("forward parent should have failed")


def test_confidence_bounds_are_enforced():
    try:
        make_packet(
            100,
            type="hypothesis",
            author="Explorer",
            claim="Invalid confidence",
            confidence=1.5,
        )
    except ValueError as exc:
        assert "confidence" in str(exc)
    else:
        raise AssertionError("invalid confidence should have failed")
