import pytest

from elysia_collective_seed.autopilot.contracts.verdict_aggregation import aggregate_candidate_gate


SHA = "adfeda71cdca2d833579fb5b949eb330a105aa4e"


class ThrowingNext:
    def __iter__(self):
        return self

    def __next__(self):
        raise RuntimeError("hostile next")


class ThrowingLength:
    def __iter__(self):
        return iter(())

    def __len__(self):
        raise RuntimeError("hostile length hint")


@pytest.mark.parametrize("malformed", (ThrowingNext(), ThrowingLength()))
@pytest.mark.parametrize("field", ("technical_results", "required_contracts"))
def test_materialization_exceptions_fail_closed(malformed, field):
    args = {"technical_results": (), "required_contracts": ("#39",)}
    args[field] = malformed
    assert aggregate_candidate_gate(
        args["technical_results"],
        human_governance_required=False,
        expected_product_sha=SHA,
        required_contracts=args["required_contracts"],
    ) == "BLOCKED_BY_TECHNICAL_VERDICT"
