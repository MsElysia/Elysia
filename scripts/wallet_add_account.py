#!/usr/bin/env python3
"""
Add a wallet sub-account (same ledger as ElysiaWallet).

Usage (from project root):
  python scripts/wallet_add_account.py "Savings pool"
  python scripts/wallet_add_account.py "Tax reserve" --id tax_reserve
  python scripts/wallet_add_account.py "Tips" --currency USD --balance 0

Copy organized_project/data/wallet_accounts.example.json to wallet_accounts.json
to auto-create accounts on wallet init.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ORG = PROJECT_ROOT / "organized_project"


def main() -> int:
    parser = argparse.ArgumentParser(description="Add an Elysia wallet sub-account")
    parser.add_argument("name", help="Display name for the account")
    parser.add_argument("--id", dest="account_id", help="Explicit account id (slug); default: derived from name")
    parser.add_argument("--type", dest="account_type", default="virtual", help="Account type (default: virtual)")
    parser.add_argument("--currency", default="USD", help="Currency code (default: USD)")
    parser.add_argument("--balance", type=float, default=0.0, help="Initial balance (default: 0)")
    args = parser.parse_args()

    if str(ORG) not in sys.path:
        sys.path.insert(0, str(ORG))
    from launcher.elysia_wallet import ElysiaWallet

    w = ElysiaWallet(api_manager=None)
    out = w.add_account(
        args.name,
        account_id=args.account_id,
        account_type=args.account_type,
        currency=args.currency,
        initial_balance=args.balance,
    )
    if out.get("success"):
        print(f"OK account_id={out.get('account_id')}")
        return 0
    print(f"ERROR: {out.get('error', out)}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
