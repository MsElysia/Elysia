#!/usr/bin/env python3
"""
Smoke-test integrated Elysia modules (same imports as elysia_sub_modules.py).
Run from project root: python scripts/verify_integrated_modules.py

Exit code 0 if all tests pass, 1 if any fail.
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "core_modules" / "elysia_core_comprehensive"))
sys.path.insert(0, str(PROJECT_ROOT / "project_guardian"))


def _ok(name: str, fn: Callable[[], Any]) -> Tuple[str, bool, str]:
    try:
        fn()
        return name, True, "ok"
    except Exception as e:
        return name, False, f"{type(e).__name__}: {e}\n{traceback.format_exc()}"


def main() -> int:
    # Avoid booting full GuardianCore from WebScout just to resolve web_reader (slow; not under test here).
    os.environ["ELYSIA_WEBSCOUT_SKIP_GUARDIAN_READER"] = "1"

    results: List[Tuple[str, bool, str]] = []

    # Hestia (optional)
    def t_hestia():
        from hestia_bridge import HestiaBridge

        HestiaBridge({}).check_hestia_running()

    results.append(_ok("hestia_bridge", t_hestia))

    # TrustEvalContent (standalone path — no guardian)
    def t_trust():
        from project_guardian.trust_eval_content import TrustEvalContent

        t = TrustEvalContent(policy_manager=None, audit_logger=None)
        assert t is not None

    results.append(_ok("trust_eval_content", t_trust))

    # FractalMind
    def t_fractal():
        from fractalmind import FractalMind

        fm = FractalMind(api_key=os.environ.get("OPENAI_API_KEY"))
        r = fm.process_task("Smoke test: list one subtask for checking the module.", depth=1, save_log=False)
        assert isinstance(r, dict) and "subtasks" in r

    results.append(_ok("fractalmind", t_fractal))

    # Harvest
    def t_harvest():
        from harvest_engine import HarvestEngine

        h = HarvestEngine()
        r = h.generate_income_report(source="gumroad")
        assert isinstance(r, dict)

    results.append(_ok("harvest_engine", t_harvest))

    # Identity
    def t_identity():
        from identity_mutation_verifier import IdentityMutationVerifier

        v = IdentityMutationVerifier()
        issues = v.check_mutation_integrity("Elysia is online", "Elysia is online")
        assert isinstance(issues, list)

    results.append(_ok("identity_mutation_verifier", t_identity))

    # Tool registry
    def t_tools():
        from ai_tool_registry import ToolRegistry, TaskRouter

        tr = ToolRegistry()
        tr.add_tool("smoke", {"provider": "test", "capabilities": ["text-gen", "general"]})
        r = TaskRouter(tr)
        out = r.route_task("text-gen", {})
        assert isinstance(out, dict) and "routed_to" in out

    results.append(_ok("ai_tool_registry", t_tools))

    # Income generator (launcher path — same as elysia_sub_income)
    def t_income_generator():
        launcher_parent = PROJECT_ROOT / "organized_project"
        if not (launcher_parent / "launcher" / "elysia_income_generator.py").exists():
            raise FileNotFoundError("organized_project/launcher/elysia_income_generator.py missing")
        if str(launcher_parent) not in sys.path:
            sys.path.insert(0, str(launcher_parent))
        from launcher.elysia_income_generator import ElysiaIncomeGenerator

        gen = ElysiaIncomeGenerator(api_manager=None)
        s = gen.get_income_summary()
        assert isinstance(s, dict) and "total_earned" in s

    results.append(_ok("income_generator", t_income_generator))

    # Wallet — Elysia’s own operating account on init
    def t_wallet_system_account():
        launcher_parent = PROJECT_ROOT / "organized_project"
        if not (launcher_parent / "launcher" / "elysia_wallet.py").exists():
            raise FileNotFoundError("organized_project/launcher/elysia_wallet.py missing")
        if str(launcher_parent) not in sys.path:
            sys.path.insert(0, str(launcher_parent))
        from launcher.elysia_wallet import ElysiaWallet, ELYSIA_SYSTEM_ACCOUNT_ID

        w = ElysiaWallet(api_manager=None)
        assert ELYSIA_SYSTEM_ACCOUNT_ID in (w.wallet.get("accounts") or {})
        aid = f"verify_smoke_{uuid.uuid4().hex[:10]}"
        r = w.add_account("Verify Smoke Bucket", account_id=aid)
        assert r.get("success") is True
        r2 = w.add_account("Verify Smoke Bucket", account_id=aid)
        assert r2.get("success") is False

    results.append(_ok("wallet_elysia_account", t_wallet_system_account))

    # WebScout agent (no network; temp proposals root)
    def t_webscout_agent():
        from webscout_agent import ElysiaWebScout

        td = Path(tempfile.mkdtemp())
        ws = ElysiaWebScout(web_reader=None, proposals_root=td, require_api_keys=False)
        lp = ws.list_proposals()
        assert isinstance(lp, list)

    results.append(_ok("webscout_agent", t_webscout_agent))

    # Implementer agent (coordinator only; temp proposals dir)
    def t_implementer_agent():
        from implementer.implementer_core import ImplementerCore

        td = Path(tempfile.mkdtemp())
        ic = ImplementerCore(td, PROJECT_ROOT, api_manager=None)
        assert ic.planner is not None and ic.task_runner is not None

    results.append(_ok("implementer_agent", t_implementer_agent))

    # Revenue creator + financial manager (launcher)
    def t_revenue_creator():
        launcher_parent = PROJECT_ROOT / "organized_project"
        if not (launcher_parent / "launcher" / "elysia_revenue_creator.py").exists():
            raise FileNotFoundError("elysia_revenue_creator.py missing")
        if str(launcher_parent) not in sys.path:
            sys.path.insert(0, str(launcher_parent))
        from launcher.elysia_revenue_creator import ElysiaRevenueCreator

        rc = ElysiaRevenueCreator(api_manager=None)
        ideas = rc.get_revenue_creation_ideas()
        assert isinstance(ideas, list)

    results.append(_ok("revenue_creator", t_revenue_creator))

    def t_financial_manager():
        launcher_parent = PROJECT_ROOT / "organized_project"
        if not (launcher_parent / "launcher" / "elysia_financial_manager.py").exists():
            raise FileNotFoundError("elysia_financial_manager.py missing")
        if str(launcher_parent) not in sys.path:
            sys.path.insert(0, str(launcher_parent))
        from launcher.elysia_financial_manager import ElysiaFinancialManager

        fm = ElysiaFinancialManager(api_manager=None, enable_real_trading=False)
        st = fm.get_financial_status()
        assert isinstance(st, dict) and "cash_balance" in st

    results.append(_ok("financial_manager", t_financial_manager))

    # LongTermPlanner (matches elysia_sub_modules kwargs)
    def t_planner():
        from longterm_planner import LongTermPlanner

        p = LongTermPlanner(runtime_loop=None, prompt_evolver=None)
        p.add_objective("SmokeObjective", "Build something small to verify planner.")
        assert len(p.list_active_objectives()) >= 1

    results.append(_ok("longterm_planner", t_planner))

    # ConsensusEngine (package import; isolated memory file)
    def t_consensus_engine():
        from project_guardian.consensus import ConsensusEngine
        from project_guardian.memory import MemoryCore

        td = Path(tempfile.mkdtemp())
        mem_path = str(td / "consensus_smoke.json")
        mem = MemoryCore(filepath=mem_path, lazy_load=True)
        ce = ConsensusEngine(mem)
        assert ce.register_agent("smoke_voter", "general") is True
        assert ce.register_agent("smoke_voter", "general") is False
        assert ce.cast_vote("smoke_voter", "smoke_action", confidence=0.9) is True
        decision = ce.decide("smoke_action")
        assert decision == "smoke_action"

    results.append(_ok("consensus_engine", t_consensus_engine))

    # ProposalSystem (temp root; watchdog started then stopped)
    def t_proposal_system():
        from project_guardian.proposal_system import ProposalSystem

        td = Path(tempfile.mkdtemp())
        ps = ProposalSystem(proposals_root=td)
        try:
            lp = ps.list_proposals()
            assert isinstance(lp, list)
        finally:
            ps.shutdown()

    results.append(_ok("proposal_system", t_proposal_system))

    # MutationEngine (isolated storage; propose + list)
    def t_mutation_engine():
        from project_guardian.mutation_engine import MutationEngine

        td = Path(tempfile.mkdtemp())
        store = td / "mutations.json"
        eng = MutationEngine(
            runtime_loop=None,
            trust_eval=None,
            ask_ai=None,
            storage_path=str(store),
        )
        chk = eng.validate_code("x = 1\n")
        assert chk.get("valid") is True
        mid = eng.propose_mutation(
            "smoke.verify_module",
            "optimization",
            "Integrated module smoke proposal",
            "x = 2\n",
            original_code="x = 1\n",
            confidence=0.5,
        )
        assert isinstance(mid, str) and len(mid) > 0
        assert eng.get_mutation(mid) is not None
        assert len(eng.list_mutations()) >= 1

    results.append(_ok("mutation_engine", t_mutation_engine))

    # SecretsManager (isolated dir; encrypt round-trip)
    def t_secrets_manager():
        from project_guardian.secrets_manager import SecretsManager

        td = Path(tempfile.mkdtemp())
        sm = SecretsManager(
            master_key_path=str(td / ".smoke_master_key"),
            secrets_dir=str(td),
            use_env_vars=False,
        )
        key = "verify_integrated_smoke"
        assert sm.set_secret(key, "roundtrip-value", save_to_file=True) is True
        assert sm.get_secret(key) == "roundtrip-value"
        assert sm.delete_secret(key) is True

    results.append(_ok("secrets_manager", t_secrets_manager))

    # API key manager singleton
    def t_api_key_manager():
        from project_guardian.api_key_manager import get_api_key_manager

        m = get_api_key_manager()
        assert m is not None
        assert hasattr(m, "keys")
        assert hasattr(m, "has_llm_access")
        assert isinstance(m.has_llm_access(), bool)

    results.append(_ok("api_key_manager", t_api_key_manager))

    # MutationReviewManager + MutationEngine (temp storage; one review)
    def t_mutation_review_manager():
        from project_guardian.mutation_engine import MutationEngine
        from project_guardian.mutation_review_manager import MutationReviewManager

        td = Path(tempfile.mkdtemp())
        eng = MutationEngine(
            runtime_loop=None,
            trust_eval=None,
            ask_ai=None,
            storage_path=str(td / "mutations.json"),
        )
        mid = eng.propose_mutation(
            "smoke.review_target",
            "optimization",
            "Review pipeline smoke",
            "y = 2\n",
            original_code="y = 1\n",
            confidence=0.6,
        )
        mgr = MutationReviewManager(
            trust_registry=None,
            trust_policy=None,
            mutation_engine=eng,
            audit_log=None,
            recovery_vault=None,
            storage_path=str(td / "mutation_reviews.json"),
        )
        review = mgr.review_mutation(mid, author="verify_smoke", require_snapshot=False)
        assert review.mutation_id == mid
        assert review.decision is not None

    results.append(_ok("mutation_review_manager", t_mutation_review_manager))

    # MutationRouter (uses review outcome → handler; engine API is get_mutation)
    def t_mutation_router():
        from project_guardian.mutation_engine import MutationEngine
        from project_guardian.mutation_review_manager import MutationReviewManager
        from project_guardian.mutation_router import MutationRouter, RouteStatus

        td = Path(tempfile.mkdtemp())
        eng = MutationEngine(
            runtime_loop=None,
            trust_eval=None,
            ask_ai=None,
            storage_path=str(td / "mutations.json"),
        )
        mid = eng.propose_mutation(
            "smoke.router_target",
            "optimization",
            "Router pipeline smoke",
            "z = 2\n",
            original_code="z = 1\n",
            confidence=0.6,
        )
        mgr = MutationReviewManager(
            trust_registry=None,
            trust_policy=None,
            mutation_engine=eng,
            audit_log=None,
            recovery_vault=None,
            storage_path=str(td / "mutation_reviews.json"),
        )
        mgr.review_mutation(mid, author="verify_router", require_snapshot=False)
        router = MutationRouter(review_manager=mgr, mutation_engine=eng, audit_log=None)
        route = router.route_mutation(mid)
        assert route.route_status == RouteStatus.COMPLETED
        assert isinstance(route.result, dict)
        assert route.result.get("success") is True

    results.append(_ok("mutation_router", t_mutation_router))

    failed = 0
    for name, ok, msg in results:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}")
        if not ok:
            print(msg)
            failed += 1
        elif msg != "ok":
            print(f"       {msg}")

    print("-" * 50)
    print(f"Total: {len(results) - failed}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
