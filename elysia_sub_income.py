#!/usr/bin/env python3
"""Elysia subroutine: Initialize income generation modules."""
import os
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def init_income_modules(modules: Dict[str, Any], project_root: Path) -> None:
    """
    Initialize income generation modules and add them to the modules dict.
    Modifies modules in place.
    """
    logger.info("  Initializing Income Generation Modules...")

    if not os.getenv("OPENAI_API_KEY") and not os.getenv("OPENROUTER_API_KEY"):
        logger.warning("  [WARN] No LLM API keys found - income modules may have limited functionality")

    api_manager = None
    launcher_path = project_root / "organized_project" / "launcher"

    # API Manager
    if (launcher_path / "api_manager.py").exists():
        try:
            import sys
            if str(launcher_path.parent) not in sys.path:
                sys.path.insert(0, str(launcher_path.parent))
            from launcher.api_manager import APIManager
            api_manager = APIManager()
            logger.info("  [OK] API Manager initialized for income modules")
        except Exception as e:
            logger.warning(f"  [WARN] API Manager import failed: {e}")

    # Income Generator
    if (launcher_path / "elysia_income_generator.py").exists():
        try:
            import sys
            if str(launcher_path.parent) not in sys.path:
                sys.path.insert(0, str(launcher_path.parent))
            from launcher.elysia_income_generator import ElysiaIncomeGenerator
            modules["income_generator"] = ElysiaIncomeGenerator(api_manager=api_manager)
            logger.info("  [OK] Income Generator initialized")
        except Exception as e:
            logger.warning(f"  [WARN] Income Generator failed: {e}")

    # Financial Manager
    if (launcher_path / "elysia_financial_manager.py").exists():
        try:
            import sys
            if str(launcher_path.parent) not in sys.path:
                sys.path.insert(0, str(launcher_path.parent))
            from launcher.elysia_financial_manager import ElysiaFinancialManager
            modules["financial_manager"] = ElysiaFinancialManager(
                api_manager=api_manager,
                enable_real_trading=False,
            )
            logger.info("  [OK] Financial Manager initialized")
        except Exception as e:
            logger.warning(f"  [WARN] Financial Manager failed: {e}")

    # Revenue Creator
    if (launcher_path / "elysia_revenue_creator.py").exists():
        try:
            import sys
            if str(launcher_path.parent) not in sys.path:
                sys.path.insert(0, str(launcher_path.parent))
            from launcher.elysia_revenue_creator import ElysiaRevenueCreator
            modules["revenue_creator"] = ElysiaRevenueCreator(api_manager=api_manager)
            logger.info("  [OK] Revenue Creator initialized")
        except Exception as e:
            logger.warning(f"  [WARN] Revenue Creator failed: {e}")

    # Wallet
    if (launcher_path / "elysia_wallet.py").exists():
        try:
            import sys
            if str(launcher_path.parent) not in sys.path:
                sys.path.insert(0, str(launcher_path.parent))
            from launcher.elysia_wallet import ElysiaWallet
            modules["wallet"] = ElysiaWallet(api_manager=api_manager)
            logger.info("  [OK] Wallet initialized")
        except Exception as e:
            logger.warning(f"  [WARN] Wallet failed: {e}")
