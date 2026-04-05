"""Feedback CLI

Simple command-line tool to collect, list, and prioritize feedback.

Features:
- Add feedback items with category, rating, and tags
- List all feedback in a readable table
- Prioritize feedback (with emphasis on improvements) using a simple scoring model
- Export feedback to a JSON file
- Clear feedback storage with confirmation flag

Storage format: JSON Lines file (one JSON object per line)
Location: <module_root>/data/feedback.jsonl
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


LOGGER = logging.getLogger(__name__)


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


@dataclass
class FeedbackRecord:
    """Structured feedback record."""

    feedback_id: str
    text: str
    category: str = "idea"  # idea | improvement | bug | question
    rating: Optional[int] = None  # 1-5
    tags: List[str] = field(default_factory=list)
    source: str = "cli"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FeedbackRepository:
    """JSONL-backed repository for feedback records."""

    def __init__(self, storage_path: Path) -> None:
        self.storage_path = storage_path
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.storage_path.exists():
            self.storage_path.touch()

    def add(self, record: FeedbackRecord) -> None:
        with self.storage_path.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        LOGGER.debug("Added feedback %s", record.feedback_id)

    def list_all(self) -> List[FeedbackRecord]:
        records: List[FeedbackRecord] = []
        with self.storage_path.open("r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    records.append(self._from_dict(data))
                except json.JSONDecodeError:
                    LOGGER.warning("Skipping invalid JSONL line")
        return records

    def clear(self) -> None:
        self.storage_path.write_text("", encoding="utf-8")
        LOGGER.info("Cleared all feedback records")

    def export(self, out_path: Path) -> None:
        records = [r.to_dict() for r in self.list_all()]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
        LOGGER.info("Exported %d records to %s", len(records), out_path)

    @staticmethod
    def _from_dict(data: Dict[str, Any]) -> FeedbackRecord:
        return FeedbackRecord(
            feedback_id=data.get("feedback_id", str(uuid.uuid4())),
            text=data.get("text", ""),
            category=data.get("category", "idea"),
            rating=data.get("rating"),
            tags=list(data.get("tags", [])),
            source=data.get("source", "cli"),
            created_at=data.get("created_at")
            or datetime.now(timezone.utc).isoformat(),
        )


class FeedbackPrioritizer:
    """Computes a simple priority score and sorts feedback accordingly."""

    CATEGORY_WEIGHTS: Dict[str, float] = {
        "improvement": 3.0,
        "bug": 2.5,
        "idea": 2.0,
        "question": 1.0,
    }

    def score(self, record: FeedbackRecord) -> float:
        category_weight = self.CATEGORY_WEIGHTS.get(record.category.lower(), 1.0)
        rating_component = 0.0
        if isinstance(record.rating, int):
            rating_component = max(1, min(5, record.rating)) * 0.6

        # Recency boost: up to +2.0 for very recent items (within ~48h)
        recency_boost = 0.0
        try:
            created = datetime.fromisoformat(record.created_at)
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600.0
            if age_hours <= 48:
                recency_boost = max(0.0, 2.0 - (age_hours / 24.0))
        except Exception:
            recency_boost = 0.0

        return category_weight + rating_component + recency_boost

    def sort(self, records: Iterable[FeedbackRecord]) -> List[FeedbackRecord]:
        return sorted(records, key=self.score, reverse=True)


def make_repository(base_dir: Optional[Path] = None) -> FeedbackRepository:
    module_root = base_dir if base_dir else Path(__file__).resolve().parent.parent
    storage = module_root / "data" / "feedback.jsonl"
    return FeedbackRepository(storage)


def cmd_add(args: argparse.Namespace) -> None:
    repo = make_repository()
    record = FeedbackRecord(
        feedback_id=str(uuid.uuid4()),
        text=args.text.strip(),
        category=args.category.lower(),
        rating=args.rating,
        tags=args.tags or [],
        source=args.source,
    )
    repo.add(record)
    LOGGER.info("Added feedback %s (%s)", record.feedback_id, record.category)


def cmd_list(args: argparse.Namespace) -> None:
    repo = make_repository()
    records = repo.list_all()
    if not records:
        print("No feedback found.")
        return
    print_table(records)


def cmd_prioritize(args: argparse.Namespace) -> None:
    repo = make_repository()
    prioritizer = FeedbackPrioritizer()
    records = repo.list_all()
    if not args.all:
        records = [r for r in records if r.category.lower() == "improvement"]
    if not records:
        print("No feedback to prioritize.")
        return
    ranked = prioritizer.sort(records)
    if args.limit is not None and args.limit > 0:
        ranked = ranked[: args.limit]
    print_table(ranked, show_score=True, prioritizer=prioritizer)


def cmd_export(args: argparse.Namespace) -> None:
    repo = make_repository()
    repo.export(Path(args.path))


def cmd_clear(args: argparse.Namespace) -> None:
    if not args.yes:
        print("Refusing to clear without --yes")
        return
    repo = make_repository()
    repo.clear()


def truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def print_table(
    records: List[FeedbackRecord],
    *,
    show_score: bool = False,
    prioritizer: Optional[FeedbackPrioritizer] = None,
) -> None:
    headers = ["ID", "Category", "Rating", "Created", "Text", "Tags"]
    if show_score:
        headers.insert(1, "Score")

    rows: List[List[str]] = []
    for r in records:
        created_short = r.created_at.split("T")[0] if r.created_at else ""
        base = [r.feedback_id.split("-")[0], r.category, str(r.rating or ""), created_short, truncate(r.text, 60), ",".join(r.tags)]
        if show_score and prioritizer is not None:
            score_str = f"{prioritizer.score(r):.2f}"
            base.insert(1, score_str)
        rows.append(base)

    col_widths: List[int] = [max(len(h), *(len(row[i]) for row in rows)) for i, h in enumerate(headers)]

    def fmt_row(cols: List[str]) -> str:
        return "  ".join(col.ljust(col_widths[i]) for i, col in enumerate(cols))

    print(fmt_row(headers))
    print("  ".join("-" * w for w in col_widths))
    for row in rows:
        print(fmt_row(row))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Feedback CLI: collect, list, and prioritize feedback",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    add_p = sub.add_parser("add", help="Add a feedback item")
    add_p.add_argument("-t", "--text", required=True, help="Feedback text")
    add_p.add_argument(
        "-c",
        "--category",
        default="idea",
        choices=["idea", "improvement", "bug", "question"],
        help="Feedback category",
    )
    add_p.add_argument("-r", "--rating", type=int, choices=[1, 2, 3, 4, 5], help="Optional rating 1-5")
    add_p.add_argument("--tags", nargs="*", help="Optional tags")
    add_p.add_argument("--source", default="cli", help="Origin of feedback")
    add_p.set_defaults(func=cmd_add)

    list_p = sub.add_parser("list", help="List all feedback")
    list_p.set_defaults(func=cmd_list)

    prio_p = sub.add_parser("prioritize", help="Show prioritized feedback")
    prio_p.add_argument("-n", "--limit", type=int, help="Limit number of items displayed")
    prio_p.add_argument("--all", action="store_true", help="Include all categories (not only improvements)")
    prio_p.set_defaults(func=cmd_prioritize)

    export_p = sub.add_parser("export", help="Export all feedback to a JSON file")
    export_p.add_argument("path", help="Output file path (e.g., exports/feedback.json)")
    export_p.set_defaults(func=cmd_export)

    clear_p = sub.add_parser("clear", help="Clear all stored feedback")
    clear_p.add_argument("--yes", action="store_true", help="Confirm clearing feedback storage")
    clear_p.set_defaults(func=cmd_clear)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    setup_logging()
    try:
        parser = build_parser()
        args = parser.parse_args(argv)
        args.func(args)
        return 0
    except KeyboardInterrupt:
        LOGGER.info("Interrupted")
        return 130
    except Exception as exc:
        LOGGER.error("Error: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())


