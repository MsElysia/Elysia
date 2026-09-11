"""Executable governance specification ONLY; no ledger or write enforcement.

The snapshot and its independently supplied current digest model a trusted
storage boundary. A digest chosen by the worker does not establish authority.
No result from this module grants permission to execute an action.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator


SCHEMA = json.loads(Path(__file__).with_name("checkpoint_snapshot.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)
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
        nodes = {n["entity_id"]: n for n in snapshot["entities"]}
        gates = {g["gate_id"]: g for g in snapshot["gates"]}
        if len(nodes) != len(snapshot["entities"]) or len(gates) != len(snapshot["gates"]):
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
                if any(p not in nodes for p in node["parent_refs"]):
                    return invalid("missing_parent")
                if any(p not in scopes for p in node["parent_refs"]):
                    continue
                objectives, lineages, refs = (set(node[k]) for k in
                    ("objective_refs", "lineage_refs", "governance_gate_refs"))
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
        applicable = [g for g in gates.values() if
            g["gate_id"] in refs or objectives.intersection(g["scope"]["objective_refs"])
            or lineages.intersection(g["scope"]["lineage_refs"])]
        effective = tuple(sorted((g["gate_id"], g["generation"]) for g in applicable))
        if any(proposal["action"] in g["blocked_actions"] for g in applicable):
            return Decision("BLOCKED_PENDING_HUMAN_RELEASE", effective, "active_or_unverified_release")
        return Decision("NO_MATCHING_BLOCK_NOT_AUTHORIZATION", effective, "other_authority_checks_required")
    except (TypeError, ValueError, KeyError, RecursionError):
        return invalid("malformed_input")
