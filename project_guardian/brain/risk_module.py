# project_guardian/brain/risk_module.py

from __future__ import annotations

import logging
import re
from typing import Iterable, Tuple

from .contracts import Observation, Plan, RiskAssessment, RiskCheckerModule, RiskLevel, StructuredCommand

logger = logging.getLogger(__name__)

_BLOCKED_PATTERNS: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\brm\s+-rf\b", re.I), "shell_destructive_rm_rf"),
    (re.compile(r"\bformat\s+c:\\b", re.I), "disk_format"),
    (re.compile(r"\bdel\s+/[sf]\b", re.I), "windows_mass_delete"),
    (re.compile(r"\bDROP\s+DATABASE\b", re.I), "sql_drop_database"),
    (re.compile(r"\bforget\s*\(\s*all\b", re.I), "memory_wipe_phrase"),
)

_HIGH_PATTERNS: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bsubprocess\.(run|call|Popen)\b", re.I), "subprocess_execution"),
    (re.compile(r"\bos\.system\b", re.I), "os_system"),
    (re.compile(r"\beval\s*\(", re.I), "eval_call"),
    (re.compile(r"\bexec\s*\(", re.I), "exec_call"),
    (re.compile(r"\bshutdown\b", re.I), "system_shutdown_word"),
)


def _match_any(text: str, patterns: Iterable[Tuple[re.Pattern[str], str]]) -> Tuple[bool, str]:
    for rx, label in patterns:
        if rx.search(text):
            return True, label
    return False, ""


class KeywordRiskChecker(RiskCheckerModule):
    def review(
        self,
        observation: Observation,
        plan: Plan,
        proposed_command: StructuredCommand,
    ) -> RiskAssessment:
        blob = " ".join(
            [
                observation.text,
                plan.goal_summary,
                proposed_command.capability_ref,
                proposed_command.audit_label,
                str(proposed_command.payload),
            ]
        )
        hit, why = _match_any(blob, _BLOCKED_PATTERNS)
        if hit:
            a = RiskAssessment(RiskLevel.BLOCKED, f"blocked_pattern:{why}", {"pattern": why})
            logger.warning("brain.risk BLOCKED %s", why)
            return a
        hit, why = _match_any(blob, _HIGH_PATTERNS)
        if hit:
            a = RiskAssessment(RiskLevel.HIGH, f"high_risk_pattern:{why}", {"pattern": why})
            logger.warning("brain.risk HIGH %s", why)
            return a
        if proposed_command.capability_ref.startswith("tool:"):
            low = RiskAssessment(RiskLevel.LOW, "tool_route_default_low", {})
            logger.info("brain.risk LOW tool route")
            return low
        return RiskAssessment(RiskLevel.MEDIUM, "module_or_mixed_default", {})
