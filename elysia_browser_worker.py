"""One bounded synthetic-store operation in the existing offline process guard."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys

CODE = Path(__file__).absolute().parent


def workspace(name: str) -> Path:
    if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,19}", name):
        raise ValueError("invalid synthetic browser store name")
    # An 8.3 path spelling is not a link. First reject symlinks/junctions
    # from the originally supplied code tree, then use the canonical directory
    # identity for the worker store and offline transaction guard.
    supplied = CODE.absolute() / ".synthetic-pilot-stores" / ("browser-" + name)
    path = CODE.resolve() / ".synthetic-pilot-stores" / ("browser-" + name)
    for candidate in (supplied, path):
        for item in reversed((candidate, *candidate.parents)):
            if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
                raise ValueError("linked synthetic workspace refused")
            if item.exists() and getattr(item.lstat(), "st_file_attributes", 0) & 0x400:
                raise ValueError("reparse synthetic workspace refused")
    if path.resolve() != path:
        raise ValueError("noncanonical synthetic workspace refused")
    if path.exists() and any(path.iterdir()):
        index = path / "synthetic-learning.json"
        if not index.is_file() or index.is_symlink():
            raise ValueError("unmarked or linked synthetic store refused")
    path.mkdir(parents=True, exist_ok=True)
    return path


def execute(name: str, command: dict) -> dict:
    path = workspace(name)
    from elysia_offline import install_offline_guard, RestrictedElysia, SYNTHETIC_MEMORIES
    denied = install_offline_guard(path)
    from elysia_synthetic_learning import SyntheticLearningStore
    system = RestrictedElysia(path)
    system.learning = SyntheticLearningStore(path, SYNTHETIC_MEMORIES)
    system.expected_snapshot = system.snapshot()
    system.start()
    try:
        operation = command["operation"]
        if operation == "inspect":
            result = {"synthetic_only": True, "providers": False, "autonomy": False,
                      "revision_limit": system.learning.MAX_REVISIONS,
                      "legacy_core_loaded": "project_guardian.core" in sys.modules,
                      "credential_manager_loaded": "project_guardian.api_key_manager" in sys.modules}
        elif operation in {"teach", "correct"}:
            key = command["key"]
            before_count = len(system.learning.facts.get(key, []))
            message = system.learning.learn(key, command["text"], correction=operation == "correct")
            written = message != "Duplicate fact; no record written."
            revisions = system.learning.history(key)
            expected_text = " ".join(command["text"].split())
            current_text = revisions[-1].split(": ", 2)[-1]
            if written:
                # Consistency validation alone cannot prove the requested commit
                # happened. Read the durable revision chain and intended bytes.
                if (len(revisions) != before_count + 1
                        or current_text != expected_text):
                    raise RuntimeError("requested durable revision was not verified")
            elif current_text.casefold() != expected_text.casefold():
                # The inherited duplicate guard searches every key and historical
                # revision. Only the requested key's current value proves a retry
                # succeeded; an older or unrelated value must remain a conflict.
                raise ValueError("duplicate does not match the requested current fact")
            result = {"message": message, "written": written}
        elif operation == "history":
            result = {"revisions": system.learning.history(command["key"])}
        elif operation == "context":
            from elysia_local_memory_chat import build_context
            result = {"bundle": build_context(system, command["query"])}
        elif operation == "source":
            source_id = command.get("source_id")
            if type(source_id) is not str or not 1 <= len(source_id) <= 160:
                raise ValueError("invalid source")
            if source_id not in system.learning.active_ids():
                raise ValueError("source is not current")
            record = system.learning.records[source_id]
            raw_bytes = (system.workspace / record["raw_source_path"]).read_bytes()
            if len(raw_bytes) > 4096:
                raise ValueError("source too large")
            digest = hashlib.sha256(raw_bytes).hexdigest()
            if digest != record["source_sha256"]:
                raise ValueError("source hash mismatch")
            revision = next((len(ids) for ids in system.learning.facts.values() if ids[-1] == source_id), None)
            if type(revision) is not int:
                raise ValueError("source is not current")
            text = raw_bytes.decode("utf-8")
            if hashlib.sha256(text.encode("utf-8")).hexdigest() != digest:
                raise ValueError("source hash mismatch")
            result = {"source_id": source_id, "source_text": text,
                      "source_sha256": digest, "revision": revision}
        elif operation == "recall":
            answer, evidence = system.respond(command["query"])
            result = {"answer": answer, "evidence": evidence}
        else:
            raise ValueError("unsupported operation")
        if denied:
            raise RuntimeError("offline boundary was violated")
        return {"ok": True, **result}
    finally:
        system.shutdown()


def main() -> int:
    command = {}
    try:
        if len(sys.argv) != 2:
            raise ValueError("one fixed synthetic store name is required")
        raw = sys.stdin.buffer.read(4097)
        if len(raw) > 4096:
            raise ValueError("request too large")
        command = json.loads(raw)
        if type(command) is not dict:
            raise ValueError("request must be an object")
        # Keep synthetic memory diagnostics and ordinary prints off the protocol.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = execute(sys.argv[1], command)
    except Exception as exc:
        # Do not emit source text, paths, credentials, or tracebacks to the browser.
        result = {"ok": False, "error": "synthetic_store_operation_failed",
                  "diagnostic": type(exc).__name__,
                  "outcome_unknown": isinstance(command, dict) and command.get("operation") in {"teach", "correct"},
                  "recovery": "Inspect the isolated store and history before retry; do not delete or reset it."}
    print(json.dumps(result, ensure_ascii=True), flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
