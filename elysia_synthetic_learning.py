"""Bounded fictional learning, using the existing source and transaction format."""
import json
import re
from pathlib import Path

from project_guardian.local_ingestion.apply_transaction import ApplyTransaction, destination_lock
from project_guardian.local_ingestion.memory_intelligence import (
    persist_source_intelligence, load_memory_intelligence_records,
    query_memory_intelligence, preserve_raw_source,
)


def store_path(name):
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", name):
        raise ValueError("Use a synthetic store name of 1-40 lowercase letters, digits, underscores or hyphens.")
    root = Path(__file__).resolve().parent / ".synthetic-pilot-stores"
    path = root / name
    if root.is_symlink() or path.is_symlink() or path.resolve() != path:
        raise ValueError("Synthetic store must be a local directory without links.")
    path.mkdir(parents=True, exist_ok=True)
    return path


class SyntheticLearningStore:
    # Three samples plus at most seven learned revisions fit the bridge limit.
    MAX_REVISIONS = 7

    def __init__(self, path, samples):
        self.path = path
        self.index = path / "synthetic-learning.json"
        self.samples = dict(samples)
        with destination_lock(path, write=True):
            if not self.index.exists():
                if any(path.iterdir()):
                    raise ValueError("Refusing an unmarked synthetic store.")
                tx = ApplyTransaction(path)
                try:
                    for identity, source in samples:
                        persist_source_intelligence(dest_dir=path, raw_bytes=source,
                                                    source_identity=identity, transaction=tx)
                    tx.write(self.index, self.encode({}))
                    tx.commit()
                except BaseException:
                    tx.abort()
                    raise
            self.validate()

    @staticmethod
    def encode(facts):
        return json.dumps({"schema": "elysia-fictional-learning-v1", "facts": facts},
                          sort_keys=True, indent=2).encode("utf-8")

    def validate(self):
        payload = json.loads(self.index.read_text(encoding="utf-8"))
        if type(payload) is not dict or set(payload) != {"schema", "facts"} or payload["schema"] != "elysia-fictional-learning-v1" or type(payload["facts"]) is not dict:
            raise ValueError("Invalid synthetic learning index.")
        facts = payload["facts"]
        records = load_memory_intelligence_records(self.path)
        # Validate all source bytes, summaries and highlight linkage via existing reader.
        query_memory_intelligence(self.path, "fictional synthetic", limit=10, validate_summaries=True)
        by_id = {r["source_id"]: r for r in records}
        expected = {preserve_raw_source(raw, source_identity=identity).source_id
                    for identity, raw in self.samples.items()}
        count = 0
        seen_text = set()
        for key, ids in facts.items():
            if not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", key) or type(ids) is not list or not ids or any(type(i) is not str for i in ids) or len(set(ids)) != len(ids):
                raise ValueError("Invalid fictional revision history.")
            for source_id in ids:
                record = by_id.get(source_id)
                if not record or record["source_identity"] != "elysia-fictional:" + key:
                    raise ValueError("Fictional history source linkage mismatch.")
                text = (self.path / record["raw_source_path"]).read_text(encoding="utf-8")
                if not text.startswith("Fictional ") or len(text) > 700 or text.casefold() in seen_text:
                    raise ValueError("Invalid or duplicate fictional fact.")
                seen_text.add(text.casefold())
                expected.add(source_id)
                count += 1
        if count > self.MAX_REVISIONS or set(by_id) != expected or len(records) != len(expected):
            raise ValueError("Unexpected synthetic records or revision capacity exceeded.")
        self.facts, self.records = facts, by_id
        return facts

    def active_ids(self):
        with destination_lock(self.path):
            self.validate()
            historical = {item for ids in self.facts.values() for item in ids[:-1]}
            return set(self.records) - historical

    def learn(self, key, text, correction=False):
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", key):
            raise ValueError("Use a lowercase fictional fact key.")
        text = " ".join(text.split())
        if not text.startswith("Fictional ") or len(text) > 700:
            raise ValueError("Fact must begin 'Fictional ' and contain at most 700 characters.")
        with destination_lock(self.path, write=True):
            facts = self.validate()
            for old_key, ids in facts.items():
                for source_id in ids:
                    old = (self.path / self.records[source_id]["raw_source_path"]).read_text(encoding="utf-8")
                    if old.casefold() == text.casefold():
                        if old_key != key or source_id != ids[-1]:
                            raise ValueError("Duplicate conflicts with the requested key's current revision.")
                        return "Duplicate fact; no record written."
            if correction != (key in facts):
                raise ValueError("Use /correct for an existing key; /teach for a new key.")
            if sum(map(len, facts.values())) >= self.MAX_REVISIONS:
                raise ValueError("This bounded pilot allows seven learned revisions per store.")
            before_count = len(facts.get(key, []))
            tx = ApplyTransaction(self.path)
            try:
                report = persist_source_intelligence(dest_dir=self.path, raw_bytes=text.encode("utf-8"),
                    source_identity="elysia-fictional:" + key, transaction=tx)
                facts.setdefault(key, []).append(report.source_id)
                tx.write(self.index, self.encode(facts))
                tx.commit()
            except BaseException:
                tx.abort()
                raise
            self.validate()
            # Both the normal console and browser must acknowledge the durable
            # requested revision, never merely the transaction method's return.
            revisions = self.history(key)
            if (len(revisions) != before_count + 1
                    or revisions[-1].split(": ", 2)[-1] != text):
                raise ValueError("Requested durable revision was not verified.")
        return "Fictional fact corrected; source history preserved." if correction else "Fictional fact learned."

    def history(self, key):
        with destination_lock(self.path):
            self.validate()
            if key not in self.facts:
                raise ValueError("No fictional fact with that key.")
            return [f"Revision {n}: {source_id}: " +
                    (self.path / self.records[source_id]["raw_source_path"]).read_text(encoding="utf-8")
                    for n, source_id in enumerate(self.facts[key], 1)]
