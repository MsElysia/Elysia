"""Deterministic dry-run harness for Elysia Collective 0.1.

This module intentionally calls no model APIs and performs no external actions.
It exists to validate packet flow, lineage, routing, critique, and synthesis rules
before the collective is wired into Guardian runtime systems.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List


VALID_TYPES = {
    "hypothesis",
    "evidence",
    "critique",
    "experiment",
    "result",
    "question",
    "synthesis",
    "proposal",
}

VALID_STATUS = {"open", "testing", "supported", "disputed", "rejected", "archived"}

ROUTE_BY_NEED = {
    "research": "Researcher",
    "critique": "Erebus",
    "experiment": "Engineer",
    "engineering": "Engineer",
    "human_review": "Human",
    "none": "Elysia",
}


@dataclass(frozen=True)
class Packet:
    packet_id: str
    type: str
    author: str
    claim: str
    confidence: float
    status: str
    parents: List[str] = field(default_factory=list)
    needs: List[str] = field(default_factory=lambda: ["none"])
    evidence: List[str] = field(default_factory=list)
    counterevidence: List[str] = field(default_factory=list)
    rationale: str = ""

    def validate(self) -> None:
        if not self.packet_id.startswith("ELY-"):
            raise ValueError("packet_id must begin ELY-")
        if self.type not in VALID_TYPES:
            raise ValueError(f"invalid packet type: {self.type}")
        if self.status not in VALID_STATUS:
            raise ValueError(f"invalid packet status: {self.status}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
        if not self.claim.strip():
            raise ValueError("claim cannot be empty")

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def route(packet: Packet) -> List[str]:
    """Return unique destination roles implied by the packet's needs."""
    destinations: List[str] = []
    for need in packet.needs:
        target = ROUTE_BY_NEED.get(need)
        if target and target not in destinations:
            destinations.append(target)
    return destinations or ["Elysia"]


def make_packet(
    seq: int,
    *,
    type: str,
    author: str,
    claim: str,
    confidence: float,
    status: str = "open",
    parents: List[str] | None = None,
    needs: List[str] | None = None,
    evidence: List[str] | None = None,
    counterevidence: List[str] | None = None,
    rationale: str = "",
) -> Packet:
    packet = Packet(
        packet_id=f"ELY-{seq:06d}",
        type=type,
        author=author,
        claim=claim,
        confidence=confidence,
        status=status,
        parents=list(parents or []),
        needs=list(needs or ["none"]),
        evidence=list(evidence or []),
        counterevidence=list(counterevidence or []),
        rationale=rationale,
    )
    packet.validate()
    return packet


def run_ec001_dry_run() -> List[Packet]:
    """Simulate one bounded packet lineage for EC-001 with fixed outputs."""
    trace: List[Packet] = []

    explorer = make_packet(
        1,
        type="hypothesis",
        author="Explorer",
        claim="Collective memory should separate immutable source history from evolving derived knowledge.",
        confidence=0.72,
        needs=["research", "critique"],
        rationale="Separating source records from derived claims limits accidental historical rewriting.",
    )
    trace.append(explorer)

    researcher = make_packet(
        2,
        type="evidence",
        author="Researcher",
        claim="Append-only provenance and explicit derived records improve auditability of collective memory.",
        confidence=0.81,
        parents=[explorer.packet_id],
        needs=["critique"],
        evidence=["design-principle: provenance", "design-principle: append-only history"],
    )
    trace.append(researcher)

    erebus = make_packet(
        3,
        type="critique",
        author="Erebus",
        claim="The proposal survives only if derived summaries never overwrite Genesis records and every synthesis cites its parents.",
        confidence=0.89,
        parents=[explorer.packet_id, researcher.packet_id],
        needs=["engineering"],
        counterevidence=["summary drift can still occur if derived packets are repeatedly summarized without source retrieval"],
        rationale="The failure mode is not storage loss but recursive distortion.",
    )
    trace.append(erebus)

    engineer = make_packet(
        4,
        type="proposal",
        author="Engineer",
        claim="Implement three memory classes with immutable Genesis records and parent-linked Collective packets.",
        confidence=0.84,
        parents=[researcher.packet_id, erebus.packet_id],
        needs=["critique"],
        rationale="This directly implements the surviving architectural constraint.",
    )
    trace.append(engineer)

    erebus2 = make_packet(
        5,
        type="critique",
        author="Erebus",
        claim="Implementation is acceptable for experiment if tests reject orphaned synthesis packets and forbidden Genesis mutation.",
        confidence=0.91,
        parents=[engineer.packet_id],
        needs=["none"],
    )
    trace.append(erebus2)

    synthesis = make_packet(
        6,
        type="synthesis",
        author="Elysia",
        claim="Current collective position: use immutable Genesis Memory plus parent-linked Collective Memory, with tests against source mutation and orphaned synthesis.",
        confidence=0.86,
        status="supported",
        parents=[explorer.packet_id, researcher.packet_id, erebus.packet_id, engineer.packet_id, erebus2.packet_id],
        needs=["none"],
    )
    trace.append(synthesis)

    return trace


def validate_trace(trace: List[Packet]) -> None:
    """Validate unique IDs, parent existence, and no self-parenting."""
    seen: set[str] = set()
    for packet in trace:
        packet.validate()
        if packet.packet_id in seen:
            raise ValueError(f"duplicate packet id: {packet.packet_id}")
        for parent in packet.parents:
            if parent == packet.packet_id:
                raise ValueError(f"packet cannot parent itself: {packet.packet_id}")
            if parent not in seen:
                raise ValueError(f"missing or forward parent {parent} for {packet.packet_id}")
        seen.add(packet.packet_id)


if __name__ == "__main__":
    packets = run_ec001_dry_run()
    validate_trace(packets)
    for packet in packets:
        print(packet.packet_id, packet.author, "->", ", ".join(route(packet)))
        print(" ", packet.claim)
