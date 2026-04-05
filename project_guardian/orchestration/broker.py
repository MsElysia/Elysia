# project_guardian/orchestration/broker.py
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from ..ollama_model_config import get_canonical_ollama_model, ollama_provider_ref
from .adapters import OllamaAdapter, OpenAIAdapter
from .pipelines import ParallelCompareAndJudgePipeline, SerialPlanExecuteReviewPipeline
from .router.rules import RulesRouter, parse_model_ref
from .telemetry.events import LLMCallEvent
from .telemetry.sqlite_store import TelemetrySqliteStore
from .types import PipelineResult, TaskRequest

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_router_raw() -> Dict[str, Any]:
    from .router import rules as rules_mod

    raw = rules_mod._load_yaml()
    if not raw and rules_mod.yaml is not None:
        raw = rules_mod.yaml.safe_load(rules_mod._DEFAULT_YAML) or {}
    return raw


class OrchestrationBroker:
    """Single public entrypoint for multi-LLM orchestration (phase 1)."""

    def __init__(
        self,
        router: Optional[RulesRouter] = None,
        telemetry: Optional[TelemetrySqliteStore] = None,
        ollama_base_url: Optional[str] = None,
    ) -> None:
        raw = _load_router_raw()
        orch = (raw.get("orchestration") or {}) if isinstance(raw, dict) else {}
        rel = orch.get("sqlite_path") or "data/orchestration_telemetry.db"
        db_path = PROJECT_ROOT / str(rel) if not Path(str(rel)).is_absolute() else Path(str(rel))
        self.telemetry = telemetry or TelemetrySqliteStore(db_path)
        self.router = router or RulesRouter(raw, telemetry_store=self.telemetry)
        self._ollama_base = ollama_base_url
        self._adapter_cache: Dict[str, Any] = {}
        self._telemetry_log = self._log_event
        self._serial = SerialPlanExecuteReviewPipeline(self.get_adapter, self._telemetry_log)
        self._parallel = ParallelCompareAndJudgePipeline(self.get_adapter, self._telemetry_log)

    async def _log_event(self, event: LLMCallEvent) -> None:
        await self.telemetry.log_call(event)

    def get_adapter(self, model_ref: str) -> Any:
        ref = (model_ref or ollama_provider_ref()).strip()
        prov, model = parse_model_ref(ref)
        if prov == "ollama":
            model = get_canonical_ollama_model(log_once=False)
        key = f"{prov}:{model}"
        if key not in self._adapter_cache:
            if prov == "ollama":
                self._adapter_cache[key] = OllamaAdapter(model, self._ollama_base)
            else:
                self._adapter_cache[key] = OpenAIAdapter(model)
        return self._adapter_cache[key]

    async def run_task(self, request: TaskRequest, *, guardian: Any = None) -> PipelineResult:
        route = await self.router.resolve(request)
        try:
            if route.pipeline_id == "parallel_compare_and_judge":
                return await self._parallel.run(request, route, guardian=guardian)
            return await self._serial.run(request, route, guardian=guardian)
        except Exception as e:
            logger.debug("[OrchestrationBroker] pipeline error: %s", e)
            return PipelineResult(
                task_id=request.task_id,
                pipeline_id=route.pipeline_id,
                success=False,
                final_output=None,
                node_results=[],
                route_reason=route.reason,
                error=str(e)[:500],
            )

    def run_task_sync(self, request: TaskRequest, *, guardian: Any = None) -> PipelineResult:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.run_task(request, guardian=guardian))

        def _run() -> PipelineResult:
            return asyncio.run(self.run_task(request, guardian=guardian))

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(_run).result(timeout=420.0)


_default_broker: Optional[OrchestrationBroker] = None


def get_orchestration_broker() -> OrchestrationBroker:
    global _default_broker
    if _default_broker is None:
        _default_broker = OrchestrationBroker()
    return _default_broker
