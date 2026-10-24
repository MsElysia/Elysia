"""Restricted synthetic startup: no live Guardian, providers or user storage.

This lane reuses the Issue #113 memory implementation and Issue #23 lifecycle
distinction. It is a bounded capability demonstration, not runtime activation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import re
import threading
import _thread
from contextlib import nullcontext

SYNTHETIC_SOURCE = b"Synthetic roofing plan: inspect the damaged flashing before replacing it."
SYNTHETIC_MEMORIES = (
    ("elysia-offline-synthetic-v1", SYNTHETIC_SOURCE),
    ("elysia-offline-garden-v1", b"Synthetic garden schedule: water the seedlings on Tuesday morning."),
    ("elysia-offline-library-v1", b"Synthetic library pickup: collect reserved books from shelf B near the front desk."),
)
# Conservative word lookup: question/filler words are not evidence of relevance.
_FILLER_WORDS = frozenset("a an and are as at be before can could do does for from how i in is it me of on or please should tell that the these this to was were what when where which will with would you your about recall remember remind retrieve day time location place".split())


class OfflineBoundaryError(RuntimeError):
    pass


def install_offline_guard(workspace: Path) -> list[str]:
    """Process lifetime containment; install only in a dedicated CLI process."""
    code = Path(__file__).resolve().parent
    data = workspace.resolve()
    runtimes = (Path(sys.base_prefix).resolve(), Path(sys.prefix).resolve())
    denied: list[str] = []
    sys.dont_write_bytecode = True

    def within(path, root):
        return path == root or root in path.parents

    def deny(detail):
        denied.append(str(detail))
        raise OfflineBoundaryError(str(detail))

    def audit(event, args):
        if event == "open" and not isinstance(args[0], int):
            path = Path(os.fsdecode(args[0])).resolve()
            flags = args[2] or 0
            writing = flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if writing and not within(path, data):
                deny("write outside synthetic workspace")
            if not writing and not within(path, data):
                if not (any(within(path, root) for root in (code, *runtimes))
                        and path.suffix.lower() in {".py", ".pyc", ".pyd", ".dll", ".zip"}):
                    deny("read outside synthetic workspace/code")
        elif event in {"os.listdir", "os.scandir"}:
            path = Path(os.fsdecode(args[0] if args[0] is not None else os.getcwd())).resolve()
            if not any(within(path, root) for root in (code, *runtimes, data)):
                deny("enumeration outside synthetic workspace/code")
        elif event in {"os.mkdir", "os.remove", "os.rmdir", "os.rename", "os.link", "os.symlink", "os.chmod", "os.truncate"}:
            # Validate both source and target for mutations which take two paths.
            paths = args[:2] if event in {"os.rename", "os.link", "os.symlink"} else args[:1]
            for value in paths:
                if not within(Path(os.fsdecode(value)).resolve(), data):
                    deny("mutation outside synthetic workspace")
        elif event.startswith(("socket.", "subprocess.")) or event in {"os.system", "os.startfile", "os.exec", "os.spawn"}:
            deny(event)
        elif event == "import" and args[0].split(".")[0] in {
            "requests", "openai", "anthropic", "httpx", "aiohttp", "numpy",
            "faiss", "sentence_transformers", "pyttsx3", "flask", "flask_socketio",
        }:
            deny("provider/model/UI import")

    sys.addaudithook(audit)
    threading.Thread.start = lambda *a, **k: deny("thread.start")
    _thread.start_new_thread = lambda *a, **k: deny("thread.start")
    if hasattr(_thread, "start_joinable_thread"):
        _thread.start_joinable_thread = lambda *a, **k: deny("thread.start")
    return denied


class RestrictedElysia:
    """Construct without activation; start only binds explicit synthetic recall."""
    def __init__(self, workspace: Path):
        self.workspace = Path(workspace)
        self.running = False
        self.bridge = None
        self.learning = None
        self.expected_snapshot = None

    def snapshot(self):
        return {str(p.relative_to(self.workspace)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.workspace.rglob("*") if p.is_file()}

    def start(self):
        if not self.running:
            from project_guardian.brain.memory_intelligence_bridge import ReadOnlyMemoryIntelligenceBridge
            self.bridge = ReadOnlyMemoryIntelligenceBridge(self.workspace)
            self.running = True

    def recall(self, query: str):
        if not self.running:
            raise OfflineBoundaryError("restricted Elysia is stopped")
        before = self.snapshot()
        if self.expected_snapshot is not None and before != self.expected_snapshot:
            raise OfflineBoundaryError("synthetic store changed outside an authorized learning command")
        active = self.learning.active_ids() if self.learning else None
        self.bridge.retrieve(query, limit=10)
        evidence = self.bridge.recall_evidence()
        if active is not None:
            evidence["hits"] = [r for r in evidence["hits"] if r["source_id"] in active]
        if before != self.snapshot():
            raise OfflineBoundaryError("recall changed synthetic files")
        return evidence

    def shutdown(self):
        self.running = False
        self.bridge = None

    def respond(self, query: str):
        """Return a deterministic answer from validated highlights, not a model."""
        if not self.running:
            raise OfflineBoundaryError("restricted Elysia is stopped")
        if self.learning:
            before = self.snapshot()
            if before != self.expected_snapshot:
                raise OfflineBoundaryError("synthetic store changed outside an authorized command")
            from offline_research_pilot import recall
            researched = recall(self.workspace, query)
            if before != self.snapshot():
                raise OfflineBoundaryError("research recall changed synthetic files")
            if researched is not None:
                return researched
        evidence = self.recall(query)
        question_words = set(re.findall(r"[^\W_]+", query.casefold()))
        terms = question_words - _FILLER_WORDS
        # The shared index intentionally permits substring matches. This small
        # pilot must not turn common words or a missing fact into an answer.
        hits = []
        covered = set()
        for row in evidence["hits"]:
            words = set(re.findall(r"[^\W_]+", " ".join(item["text"] for item in row["highlights"]).casefold()))
            # These fixed samples have one schedule and one pickup location.
            # Topic overlap alone cannot supply a missing time or location.
            if question_words & {"when", "day", "time"} and not words & {"tuesday", "morning"}:
                continue
            if question_words & {"where", "location", "place"} and not words & {"shelf", "desk"}:
                continue
            # A complete question must be supported by one source. Combining
            # unrelated records cannot establish a missing fictional fact.
            matching = terms & words if terms <= words else set()
            if matching:
                hits.append(row)
                covered.update(matching)
        evidence["hits"] = hits if terms and terms <= covered else []
        evidence["relevant_context_ids"] = [row["chunk_id"] for row in evidence["hits"]]
        highlights = [item for row in evidence["hits"] for item in row["highlights"]]
        if not highlights:
            return "No matching synthetic memory was found.", evidence
        answer = "From synthetic memory: " + " ".join(item["text"] for item in highlights)
        return answer, evidence


def interactive_session(system: RestrictedElysia):
    """One existing restricted system, multiple ephemeral input turns."""
    state = {"query": None, "answer": "", "recall": None,
             "turn_count": 0, "unavailable_count": 0, "restart_count": 0}
    print("Elysia offline pilot ready. Synthetic memories only; no personal data.", flush=True)
    print("Try: damaged flashing; water seedlings; reserved library books.", flush=True)
    print("Commands: /help, /memories, /restart, /exit. Answers quote recorded facts; no inference.", flush=True)
    if system.learning:
        print("Persistent fictional learning and offline research are ready. Internet and providers disabled.", flush=True)
        print("Teach: /teach key | Fictional fact. Correct: /correct key | Fictional fact. History: /history key.", flush=True)
        print("Research: /research Skylark Composite. Enter /exit to close; launch again to recall saved evidence.", flush=True)
    while True:
        print("Ask Elysia:", flush=True)
        try:
            raw = sys.stdin.readline(802)
        except KeyboardInterrupt:
            print("Exit requested.", flush=True)
            break
        if not raw:
            print("Input closed. Exiting.", flush=True)
            break
        query = raw.rstrip("\r\n")
        if len(query) > 800:
            # Discard the rest of this one oversized line, never treat its tail
            # as a second question or command.
            while raw and not raw.endswith("\n"):
                raw = sys.stdin.readline(802)
            print("Please use a question of 1 to 800 characters.", flush=True)
            continue
        if not query.strip():
            print("Enter a synthetic question or /exit.", flush=True)
            continue
        command = query.strip().casefold()
        if command.startswith("/research "):
            if system.learning is None:
                print("Research requires --synthetic-store NAME. Controlled fictional fixtures only; internet disabled.", flush=True)
                continue
            if system.snapshot() != system.expected_snapshot:
                raise OfflineBoundaryError("synthetic store changed outside research")
            from offline_research_pilot import research
            try:
                print("Offline restricted mode. Bounded plan: five approved synthetic sources; 2048 bytes per source; zero network/model calls.", flush=True)
                report = research(system.workspace, query.strip().split(" ", 1)[1])
                print(f"Controlled synthetic research: {len(report['accepted'])} new sources preserved; {len(report['conflicts'])} unresolved potential conflicts.", flush=True)
                for item in report["accepted"]:
                    print(f"Preserved {item['url']} SHA256: {item['sha256']} Evidence: {item['source_id']}", flush=True)
                for item in report["rejected"]:
                    print(f"Rejected {item['url']}: {item['reason']}", flush=True)
                system.expected_snapshot = system.snapshot()
                state.update(query=None, answer="", recall=None)
            except ValueError as exc:
                print(f"Research unavailable: {exc}", flush=True)
            continue
        if command.startswith(("/teach ", "/correct ", "/history ")):
            if system.learning is None:
                print("Learning requires --synthetic-store NAME. Use fictional data only.", flush=True)
                continue
            if system.snapshot() != system.expected_snapshot:
                raise OfflineBoundaryError("synthetic store changed outside learning")
            verb, rest = query.strip().split(" ", 1)
            try:
                if verb.casefold() == "/history":
                    for line in system.learning.history(rest.strip()):
                        print(line, flush=True)
                else:
                    key, separator, fact = rest.partition("|")
                    if not separator:
                        raise ValueError("Use /teach key | Fictional fact, or /correct key | Fictional fact.")
                    print(system.learning.learn(key.strip(), fact.strip(), verb.casefold() == "/correct"), flush=True)
                    system.expected_snapshot = system.snapshot()
                    state.update(query=None, answer="", recall=None)
            except ValueError as exc:
                print(f"Learning unavailable: {exc}", flush=True)
            continue
        if command in {"/exit", "/quit", "exit", "quit"}:
            print("Exit requested.", flush=True)
            break
        if command == "/help":
            print("Ask with words from the samples. /memories shows all synthetic facts; /restart reopens them; /exit ends the session.", flush=True)
            print("Persistent fictional mode: --interactive --synthetic-store NAME. /teach key | Fictional fact; /correct key | Fictional fact; /history key.", flush=True)
            print("/research Skylark Composite researches five controlled fictional sources. No internet research.", flush=True)
            continue
        if command == "/memories":
            for _, source in SYNTHETIC_MEMORIES:
                print(source.decode("utf-8"), flush=True)
            continue
        if command == "/restart":
            system.shutdown()
            system.start()
            if state["query"] is not None:
                answer, recall = system.respond(state["query"])
                if answer != state["answer"] or recall != state["recall"]:
                    raise OfflineBoundaryError("interactive restart changed recalled evidence")
            state["restart_count"] += 1
            print("Restart complete. Synthetic memories retained.", flush=True)
            continue
        if command.startswith("/"):
            print("Unknown command. Use /help or /exit.", flush=True)
            continue
        answer, recall = system.respond(query)
        state.update(query=query, answer=answer, recall=recall)
        state["turn_count"] += 1
        if not recall["hits"]:
            state["unavailable_count"] += 1
            print("Elysia: Information unavailable. " + answer, flush=True)
        else:
            print("Elysia: " + answer, flush=True)
    return state


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Restricted offline startup (the draft default)")
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--query", default="roofing flashing", help="Query the fixed synthetic fixture only")
    inputs.add_argument("--stdin", action="store_true", help="Read one synthetic question after startup")
    inputs.add_argument("--interactive", action="store_true", help="Ask multiple synthetic questions in one session")
    parser.add_argument("--demo", action="store_true", help="Show a readable one-turn offline demonstration")
    parser.add_argument("--synthetic-store", help="Retain only invented facts in a named isolated pilot store")
    args = parser.parse_args(argv)
    # Deliberately no destination option, environment config or user-memory read.
    try:
        if args.synthetic_store:
            from elysia_synthetic_learning import store_path
            context = nullcontext(store_path(args.synthetic_store))
        else:
            context = tempfile.TemporaryDirectory(prefix="elysia-offline-")
        with context as directory:
            workspace = Path(directory)
            denied = install_offline_guard(workspace)
            system = RestrictedElysia(workspace)
            try:
                from project_guardian.local_ingestion.memory_intelligence import persist_source_intelligence
                if args.synthetic_store:
                    from elysia_synthetic_learning import SyntheticLearningStore
                    system.learning = SyntheticLearningStore(workspace, SYNTHETIC_MEMORIES)
                else:
                    for identity, source in SYNTHETIC_MEMORIES:
                        persist_source_intelligence(dest_dir=workspace, raw_bytes=source,
                                                    source_identity=identity)
                def snapshot():
                    return {str(p.relative_to(workspace)): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in workspace.rglob("*") if p.is_file()}
                before = snapshot()
                system.expected_snapshot = before
                system.start()
                if args.demo and not args.interactive:
                    print("Elysia offline startup complete. Synthetic memory is ready.", flush=True)
                if args.interactive:
                    state = interactive_session(system)
                    query, answer, first = state["query"], state["answer"], state["recall"]
                elif args.stdin:
                    if args.demo:
                        print("Enter one synthetic question:", flush=True)
                    query = sys.stdin.readline(802)
                    if not query or len(query.rstrip("\r\n")) > 800:
                        raise ValueError("one synthetic question of 1 to 800 characters is required")
                    query = query.rstrip("\r\n")
                else:
                    query = args.query
                if not args.interactive and (not query.strip() or len(query) > 800):
                    raise ValueError("one synthetic question of 1 to 800 characters is required")
                if args.demo and not args.interactive:
                    print(f"Synthetic input: {query}", flush=True)
                if not args.interactive:
                    answer, first = system.respond(query)
                if args.demo and not args.interactive:
                    print(f"Memory retrieval: {len(first['hits'])} source-validated hit(s).", flush=True)
                    print(f"Elysia: {answer}", flush=True)
                system.shutdown()
                system.start()
                second_answer, second = system.respond(query) if query is not None else (answer, first)
                system.shutdown()
                if denied or first != second or answer != second_answer or system.expected_snapshot != snapshot():
                    raise OfflineBoundaryError("containment or restart/read-only verification failed")
                payload = {"classification": "restricted_offline_runtime_verified",
                              "synthetic_only": True, "recall": first,
                              "answer": answer,
                              "restart_equal": True, "recall_wrote_files": False,
                              "running_after_shutdown": system.running,
                              "denied_effects": denied,
                              "legacy_core_loaded": "project_guardian.core" in sys.modules,
                              "threads": [t.name for t in threading.enumerate()]}
                if payload["threads"] != ["MainThread"] or payload["legacy_core_loaded"]:
                    raise OfflineBoundaryError("unexpected legacy import or remaining background thread")
            finally:
                system.shutdown()
        # Success is emitted only after temporary-data cleanup completed.
        payload["temporary_data_removed"] = not workspace.exists()
        if (not args.synthetic_store and not payload["temporary_data_removed"]) or denied:
            raise OfflineBoundaryError("temporary-data cleanup verification failed")
        if args.interactive:
            print(f"Session ended: {state['turn_count']} questions; {state['unavailable_count']} unavailable; {state['restart_count']} restarts.", flush=True)
            if args.synthetic_store:
                print("Security evidence: " + json.dumps(payload, sort_keys=True), flush=True)
        if args.demo or args.interactive:
            print("Shutdown complete. Named fictional store retained." if args.synthetic_store else "Shutdown complete. Temporary synthetic data removed.", flush=True)
        else:
            print(json.dumps(payload, sort_keys=True))
        return 0
    except (ValueError, OSError, OfflineBoundaryError) as exc:
        print(f"Offline startup failed: {exc}", file=sys.stderr)
        return 2
