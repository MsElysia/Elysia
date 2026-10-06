"""Issue #43 synthetic coordination model ONLY; no live store or authority.

Pins and complete inventory are supplied by a fixture-owned model boundary.
The lock models a linearization point; it proves no production transaction,
authentication, physical durability or restart-safe high-water mark.
"""
from copy import deepcopy
import json
from pathlib import Path
from threading import RLock

from jsonschema import Draft202012Validator, ValidationError

from .admission import evaluate_admitted
from .checkpoint_reference import snapshot_digest


SCHEMA = json.loads(Path(__file__).with_name("current_manifest.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA)
POINTER_VALIDATOR = Draft202012Validator({"$defs": SCHEMA["$defs"], "$ref": "#/$defs/pointer"})


def decode(raw):
    """Reject duplicate keys/nonfinite JSON before canonicalizing identity."""
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError("duplicate_json_key")
            out[key] = value
        return out
    def nonfinite(value):
        raise ValueError("nonfinite_json")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def _exact_integers(value):
    # Schema integer includes integral floats; this contract deliberately does not.
    if isinstance(value, dict):
        for key, child in value.items():
            if key.endswith("generation") or key.endswith("version"):
                if type(child) is not int or child < 1:
                    raise ValueError("nonexact_generation_or_version")
            _exact_integers(child)
    elif isinstance(value, list):
        for child in value:
            _exact_integers(child)


def pointer(manifest):
    return {"pointer_schema_version": 1,
            "control_plane_ref": manifest["control_plane_ref"],
            "repository": manifest["repository"],
            "manifest_generation": manifest["manifest_generation"],
            "manifest_digest": snapshot_digest(manifest)}


def _check_manifest(manifest, inventory, snapshot, pins):
    _exact_integers(manifest)
    _exact_integers(snapshot)
    VALIDATOR.validate(manifest)
    if manifest["repository"] != pins["repository"] or manifest["control_plane_ref"] != pins["control_plane_ref"]:
        raise ValueError("identity_pin_mismatch")
    if snapshot_digest(inventory) != pins["inventory_digest"] or snapshot_digest(snapshot) != pins["snapshot_digest"]:
        raise ValueError("independent_pin_mismatch")
    if manifest["coverage"] != {"inventory_ref": pins["inventory_ref"],
                                "inventory_digest": pins["inventory_digest"],
                                "item_ids": sorted(inventory), "unresolved_sources": []}:
        raise ValueError("incomplete_coverage")
    if manifest["governance_snapshot"] != {"ref": pins["snapshot_ref"],
                                          "digest": pins["snapshot_digest"],
                                          "snapshot_generation": snapshot["snapshot_generation"]}:
        raise ValueError("snapshot_pin_mismatch")
    if manifest["retained_boundaries"]["snapshot_digest"] != pins["snapshot_digest"]:
        raise ValueError("boundary_snapshot_mismatch")
    records = {r["item_id"]: r for r in manifest["routing_records"]}
    if len(records) != len(manifest["routing_records"]) or records != inventory:
        raise ValueError("inventory_or_claim_binding_mismatch")
    for record in records.values():
        claims = record["claims"]
        if len({c["claim_id"] for c in claims}) != len(claims):
            raise ValueError("duplicate_claim_identity")
        if record["blockers"] or any(c["state"] in ("FAIL", "UNPROVEN", "PARTIAL", "BLOCKED", "UNAUTHORIZED_BUT_PRESERVED_EVIDENCE") for c in claims):
            if record["disposition"] != "BLOCKED":
                raise ValueError("unresolved_claim_promotion")
        decision = evaluate_admitted(snapshot, record["entity_id"], record["action"],
                                     trusted_current_digest=pins["snapshot_digest"],
                                     minimum_generation=snapshot["snapshot_generation"])
        if decision.disposition == "BLOCKED_INVALID_STATE":
            raise ValueError("invalid_admitted_routing")
        if decision.disposition == "BLOCKED_PENDING_HUMAN_RELEASE" and record["disposition"] != "BLOCKED":
            raise ValueError("gate_conflicting_routing")


class ModelStore:
    """Disposable fixture store. Never instantiate against live project state.

    Bootstrap is fixture-only. Candidate preparation can leave unreachable
    immutable bytes; acceptance is a diagnostic pointer transition only.
    """
    def __init__(self, initial, inventory, snapshot, pins, *, atomic=True):
        _check_manifest(initial, inventory, snapshot, pins)
        self._lock = RLock()
        self._objects = {snapshot_digest(initial): json.dumps(initial, sort_keys=True, separators=(",", ":"), allow_nan=False)}
        self._pointer = pointer(initial)
        self._dependencies = {snapshot_digest(initial): deepcopy((inventory, snapshot, pins))}
        self._inventory = deepcopy(inventory)
        self._snapshot = deepcopy(snapshot)
        self._pins = deepcopy(pins)
        self.atomic = atomic

    def read(self):
        with self._lock:
            try:
                _exact_integers(self._pointer)
                POINTER_VALIDATOR.validate(self._pointer)
                manifest = decode(self._objects[self._pointer["manifest_digest"]])
                if pointer(manifest) != self._pointer:
                    raise ValueError("pointer_digest_mismatch")
                _exact_integers(manifest)
                VALIDATOR.validate(manifest)
                _check_manifest(manifest, *self._dependencies[self._pointer["manifest_digest"]])
                return deepcopy(self._pointer), manifest
            except (ValidationError, ValueError, TypeError, KeyError, RecursionError) as exc:
                raise ValueError("unavailable_current_state") from exc

    def state_bytes(self):
        with self._lock:
            return deepcopy(self._pointer), deepcopy(self._objects), deepcopy(self._dependencies)

    def replace_fixture_sources(self, inventory, snapshot, pins):
        # Test-only revision change, not a live acquisition or release API.
        with self._lock:
            self._inventory, self._snapshot, self._pins = map(deepcopy, (inventory, snapshot, pins))

    def prepare(self, raw, *, fail_materialization=False):
        with self._lock:
            try:
                candidate = decode(raw)
                current, old = self.read()
                _check_manifest(candidate, self._inventory, self._snapshot, self._pins)
                token = pointer(candidate)
                if token == current:
                    return "ALREADY_CURRENT", None
                if candidate["predecessor"] != current:
                    return "STALE_PREDECESSOR", None
                if candidate["manifest_generation"] != current["manifest_generation"] + 1:
                    raise ValueError("nonsequential_generation")
                # This bounded slice allows routing-only changes with a fixed gate snapshot.
                if candidate["governance_snapshot"] != old["governance_snapshot"]:
                    raise ValueError("gate_snapshot_change_out_of_scope")
                new = {r["item_id"]: r for r in candidate["routing_records"]}
                for previous in old["routing_records"]:
                    successor = new[previous["item_id"]]
                    for key in previous:
                        if key in ("claims", "blockers"):
                            if any(x not in successor[key] for x in previous[key]):
                                raise ValueError("dropped_history_or_blocker")
                        elif successor[key] != previous[key]:
                            raise ValueError("changed_existing_binding_or_disposition")
                if fail_materialization:
                    return "MATERIALIZATION_UNAVAILABLE", None
                data = json.dumps(candidate, sort_keys=True, separators=(",", ":"), allow_nan=False)
                digest = token["manifest_digest"]
                if digest in self._objects and self._objects[digest] != data:
                    raise ValueError("immutable_object_conflict")
                self._objects[digest] = data
                self._dependencies[digest] = deepcopy((self._inventory, self._snapshot, self._pins))
                return "PREPARED", {"candidate": token, "predecessor": current, "source_pins": deepcopy(self._pins)}
            except Exception:
                # Model inputs are hostile JSON; schema errors are diagnostics.
                return "BLOCKED_INVALID_STATE", None

    def commit(self, receipt):
        with self._lock:
            if not self.atomic:
                return "ATOMIC_ACCEPTANCE_UNAVAILABLE"
            try:
                if type(receipt) is not dict or set(receipt) != {"candidate", "predecessor", "source_pins"}:
                    raise ValueError("receipt_shape")
                for token in (receipt["candidate"], receipt["predecessor"]):
                    _exact_integers(token)
                    POINTER_VALIDATOR.validate(token)
                current, old = self.read()
                candidate = decode(self._objects[receipt["candidate"]["manifest_digest"]])
                dependencies = self._dependencies[receipt["candidate"]["manifest_digest"]]
                _check_manifest(candidate, *dependencies)
                if dependencies[2] != receipt["source_pins"]:
                    raise ValueError("dependency_pin_mismatch")
                if pointer(candidate) != receipt["candidate"] or candidate["predecessor"] != receipt["predecessor"]:
                    raise ValueError("receipt_binding")
                if receipt["source_pins"] != self._pins:
                    return "STALE_SOURCE"
                _check_manifest(candidate, self._inventory, self._snapshot, self._pins)
                if current == receipt["candidate"]:
                    return "ALREADY_CURRENT"
                if current != receipt["predecessor"]:
                    return "STALE_PREDECESSOR"
                # Revalidate preparation at the commit boundary, including retention.
                status, checked = self.prepare(self._objects[receipt["candidate"]["manifest_digest"]])
                if status != "PREPARED" or checked != receipt:
                    return status if status != "PREPARED" else "BLOCKED_INVALID_STATE"
                self._pointer = deepcopy(receipt["candidate"])
                return "ACCEPTED_MODEL_POINTER_NOT_AUTHORIZATION"
            except Exception:
                return "BLOCKED_INVALID_STATE"
