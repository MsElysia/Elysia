#!/usr/bin/env python3
"""Elysia subroutine: Register modules with Architect-Core."""
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

MODULE_REGISTRY = {
    "TrustEvalContent": {
        "name": "TrustEvalContent",
        "version": "1.0",
        "role": "safety",
        "exposed_interfaces": ["evaluate", "sanitize_content"],
    },
    "FractalMind": {
        "name": "FractalMind",
        "version": "1.0",
        "role": "planning",
        "exposed_interfaces": ["process_task", "generate_subtasks"],
    },
    "HarvestEngine": {
        "name": "HarvestEngine",
        "version": "1.0",
        "role": "financial",
        "exposed_interfaces": ["generate_income_report", "get_account_status"],
    },
    "IdentityMutationVerifier": {
        "name": "IdentityMutationVerifier",
        "version": "1.0",
        "role": "safety",
        "exposed_interfaces": ["verify_mutation", "check_mutation_integrity"],
    },
    "AIToolRegistry": {
        "name": "AIToolRegistry",
        "version": "1.0",
        "role": "infrastructure",
        "exposed_interfaces": ["add_tool", "route_task", "list_tools"],
    },
    "LongTermPlanner": {
        "name": "LongTermPlanner",
        "version": "1.0",
        "role": "planning",
        "exposed_interfaces": ["add_objective", "schedule_objective", "export_plan"],
    },
    "IncomeGenerator": {
        "name": "IncomeGenerator",
        "version": "1.0",
        "role": "financial",
        "exposed_interfaces": ["generate_income", "list_strategies", "get_income_status"],
    },
    "FinancialManager": {
        "name": "FinancialManager",
        "version": "1.0",
        "role": "financial",
        "exposed_interfaces": ["get_balance", "track_investments", "set_financial_goals"],
    },
    "RevenueCreator": {
        "name": "RevenueCreator",
        "version": "1.0",
        "role": "financial",
        "exposed_interfaces": ["create_revenue_project", "list_projects"],
    },
    "Wallet": {
        "name": "Wallet",
        "version": "1.0",
        "role": "financial",
        "exposed_interfaces": ["get_balance", "deposit", "withdraw"],
    },
}


def register_all_modules(architect: Optional[Any]) -> None:
    """
    Register all modules with Architect-Core.
    """
    logger.info("[5/5] Registering modules with Architect-Core...")

    if not architect:
        logger.warning("  [WARN] Architect-Core not available, skipping registration")
        return

    for module_name, module_data in MODULE_REGISTRY.items():
        try:
            architect.register_new_module(module_data)
            logger.info(f"  [OK] Registered {module_name}")
        except Exception as e:
            logger.warning(f"  [WARN] Failed to register {module_name}: {e}")

    logger.info("  [OK] Module registration complete")
