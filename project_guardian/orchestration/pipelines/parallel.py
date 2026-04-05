# project_guardian/orchestration/pipelines/parallel.py
from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable, List

from ..judge.deterministic import DeterministicJudge, pick_best_node, strip_json_fence
from ..judge.model_judge import ModelJudge
from ...ollama_model_config import ollama_provider_ref
from ..router.rules import parse_model_ref
from ..types import NodeResult, PipelineResult, RouteDecision, TaskRequest
from .nodes import run_llm_node
from ...prompts.prompt_builder import build_prompt

logger = logging.getLogger(__name__)


class ParallelCompareAndJudgePipeline:
    pipeline_id = "parallel_compare_and_judge"

    def __init__(
        self,
        get_adapter: Callable[[str], Any],
        telemetry_log: Callable[[Any], Awaitable[None]],
    ) -> None:
        self._get_adapter = get_adapter
        self._telemetry_log = telemetry_log
        self._det = DeterministicJudge()

    async def run(self, request: TaskRequest, route: RouteDecision, guardian: Any = None) -> PipelineResult:
        fan = list(route.fanout_models or [])
        if len(fan) < 2:
            fan = [route.planner_model or ollama_provider_ref(), route.executor_model or "openai:gpt-4.1-mini"]
        a_ref, b_ref = fan[0], fan[1]
        if parse_model_ref(a_ref) == parse_model_ref(b_ref):
            b_ref = "openai:gpt-4.1-mini" if parse_model_ref(a_ref)[0] == "ollama" else ollama_provider_ref()

        nodes: List[NodeResult] = []
        adapt_a = self._get_adapter(a_ref)
        adapt_b = self._get_adapter(b_ref)

        sys_a = build_prompt(
            "planner",
            "orchestrator",
            task_text="Branch A: answer the user task.",
            extra_rules=["Independent phrasing from branch B."],
        )
        sys_b = build_prompt(
            "planner",
            "orchestrator",
            task_text="Branch B: answer the user task.",
            extra_rules=["Independent phrasing from branch A."],
        )
        prompt = request.prompt[:24_000]

        nr_a = await run_llm_node(
            node_id="fanout_a",
            adapter=adapt_a,
            task_id=request.task_id,
            task_type=request.task_type,
            pipeline_id=self.pipeline_id,
            prompt=prompt,
            system=sys_a,
            telemetry_log=self._telemetry_log,
            temperature=0.35,
        )
        nr_b = await run_llm_node(
            node_id="fanout_b",
            adapter=adapt_b,
            task_id=request.task_id,
            task_type=request.task_type,
            pipeline_id=self.pipeline_id,
            prompt=prompt,
            system=sys_b,
            telemetry_log=self._telemetry_log,
            temperature=0.35,
        )
        nodes.extend([nr_a, nr_b])

        det = await self._det.compare([nr_a, nr_b], request)
        nodes.append(det)

        winner = pick_best_node([nr_a, nr_b])
        chosen = winner.output
        if det.review_verdict == "inconclusive" and route.judge_model:
            try:
                j_adapt = self._get_adapter(route.judge_model)
                jp, jm = parse_model_ref(route.judge_model)
                if (jp, jm) not in {parse_model_ref(a_ref), parse_model_ref(b_ref)} or jp == "openai":
                    mj = ModelJudge(j_adapt)
                    mres = await mj.compare([nr_a, nr_b], request)
                    nodes.append(mres)
                    chosen = mres.output
            except Exception as e:
                logger.debug("parallel model judge skipped: %s", e)

        ft = strip_json_fence(str(chosen or ""))
        parsed: Any = ft
        try:
            if ft.strip().startswith("{"):
                parsed = json.loads(ft)
        except Exception:
            parsed = ft

        ok = bool(str(ft).strip())
        return PipelineResult(
            task_id=request.task_id,
            pipeline_id=self.pipeline_id,
            success=ok,
            final_output=parsed,
            node_results=nodes,
            route_reason=route.reason,
            error=None if ok else "parallel_judge_failed",
        )
