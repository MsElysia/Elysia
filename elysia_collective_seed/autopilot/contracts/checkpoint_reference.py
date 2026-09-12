"""Executable governance specification ONLY; no ledger or write enforcement.

The snapshot and its independently supplied current digest model a trusted
storage boundary. A digest chosen by the worker does not establish authority.
No result from this module grants permission to execute an action.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator, FormatChecker


SCHEMA = json.loads(Path(__file__).with_name("checkpoint_snapshot.schema.json").read_text(encoding="utf-8"))
FORMAT_CHECKER = FormatChecker()
RFC3339 = re.compile(
    r"^(?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})T"
    r"(?P<hour>[0-9]{2}):(?P<minute>[0-9]{2}):(?P<second>[0-9]{2})"
    r"(?:\.[0-9]+)?(?P<zone>Z|[+-](?P<zone_hour>[0-9]{2}):(?P<zone_minute>[0-9]{2}))$"
)


@FORMAT_CHECKER.checks("date-time", raises=(TypeError, ValueError))
def _is_rfc3339_datetime(value):
    if not isinstance(value, str):
        return False
    match = RFC3339.fullmatch(value)
    if match is None:
        return False
    parts = {name: int(match.group(name)) for name in
             ("year", "month", "day", "hour", "minute", "second")}
    if parts["second"] > 60 or parts["hour"] > 23 or parts["minute"] > 59:
        return False
    if match.group("zone") != "Z" and (
            int(match.group("zone_hour")) > 23
            or int(match.group("zone_minute")) > 59):
        return False
    # datetime validates calendar dates. RFC 3339 permits the leap-second value
    # 60, so use 59 solely for calendar validation after checking the bound.
    datetime(parts["year"], parts["month"], parts["day"], parts["hour"],
             parts["minute"], min(parts["second"], 59))
    return True


VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FORMAT_CHECKER)
ACTIONS = frozenset(SCHEMA["$defs"]["action"]["enum"])


@dataclass(frozen=True)
class Decision:
    disposition: str
    effective_active_gates: tuple[tuple[str, int], ...] = ()
    reason: str = ""
    release_validation: str = "UNAVAILABLE"
    external_write_enforcement: str = "NOT_ENFORCED"


def snapshot_digest(snapshot: dict) -> str:
    """Content identity, NOT an authentication or human-presence mechanism."""
    data = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def evaluate(snapshot, proposal, *, trusted_current_digest, checkpoint=None) -> Decision:
    """Compare a proposed action with pinned machine state, ignoring prose.

`checkpoint` is deliberately non-authoritative, including every release claim.
The caller must obtain proposal classification/ancestry and the current digest
from independent trusted admission/storage. This oracle does not provide them.
Malformed or incomplete state blocks; released records remain effective because
no human-controlled release trust anchor has been selected.
"""
    invalid = lambda reason: Decision("BLOCKED_INVALID_STATE", reason=reason)
    try:
        if not isinstance(snapshot, dict) or not VALIDATOR.is_valid(snapshot):
            return invalid("snapshot_schema")
        if type(trusted_current_digest) is not str or snapshot_digest(snapshot) != trusted_current_digest:
            return invalid("snapshot_not_current_or_not_pinned")
        if (type(proposal) is not dict or set(proposal) != {"entity_id", "action"}
                or type(proposal["entity_id"]) is not str
                or type(proposal["action"]) is not str or proposal["action"] not in ACTIONS):
            return invalid("proposal_schema")
        nodes = {n["entity_id"]: n for n in snapshot["admissions"]}
        gates = {g["gate_id"]: g for g in snapshot["gates"]}
        authorities = {(a["authority_id"], a["authority_generation"]): a for a in snapshot["admission_authorities"]}
        if (len(nodes) != len(snapshot["admissions"]) or len(gates) != len(snapshot["gates"])
                or len(authorities) != len(snapshot["admission_authorities"])):
            return invalid("duplicate_identity")
        if proposal["entity_id"] not in nodes:
            return invalid("unknown_entity")

        # Validate the entire graph, including disconnected records. Iterative
        # traversal avoids recursion-depth failures on deeply subdivided tasks.
        scopes = {}
        pending = set(nodes)
        while pending:
            progressed = False
            for key in sorted(pending):
                node = nodes[key]
                authority = node["admitted_by"]
                if (authority["authority_id"], authority["authority_generation"]) not in authorities:
                    return invalid("unknown_admission_authority")
                if any(p not in nodes for p in node["parent_refs"]):
                    return invalid("missing_parent")
                if any(p not in scopes for p in node["parent_refs"]):
                    continue
                objectives = set(node["objective_refs"])
                lineages = set(node["repository_lineage_refs"]) | set(node["governance_lineage_refs"])
                refs = set(node["governance_gate_refs"])
                for parent in node["parent_refs"]:
                    for target, inherited in zip((objectives, lineages, refs), scopes[parent]):
                        target.update(inherited)
                if any(ref not in gates for ref in refs):
                    return invalid("missing_gate")
                scopes[key] = objectives, lineages, refs
                pending.remove(key)
                progressed = True
            if not progressed:
                return invalid("ancestry_cycle")

        objectives, lineages, refs = scopes[proposal["entity_id"]]
        if proposal["action"] not in nodes[proposal["entity_id"]]["action_classes"]:
            return invalid("action_not_admitted")
        applicable = [g for g in gates.values() if
            g["gate_id"] in refs or objectives.intersection(g["scope"]["objective_refs"])
            or lineages.intersection(g["scope"]["lineage_refs"])]
        effective = tuple(sorted((g["gate_id"], g["generation"]) for g in applicable))
        if any(proposal["action"] in g["blocked_actions"] for g in applicable):
            return Decision("BLOCKED_PENDING_HUMAN_RELEASE", effective, "active_or_unverified_release")
        return Decision("NO_MATCHING_BLOCK_NOT_AUTHORIZATION", effective, "other_authority_checks_required")
    except (TypeError, ValueError, KeyError, RecursionError):
        return invalid("malformed_input")
