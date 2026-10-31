"""Manual operator entry point; never accepts serialized authorization or receipts."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_guardian.verified_local_calculation import OperatorCalculationSession


def main():
    parser = argparse.ArgumentParser(description="Authorize one local labor calculation; no external effect.")
    parser.add_argument("--workspace", type=Path, required=True, help="Disposable synthetic application state directory")
    parser.add_argument("--rate")
    parser.add_argument("--painters", type=int)
    parser.add_argument("--days", type=int)
    parser.add_argument("--hours-per-day", type=int)
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if not args.status and any(v is None for v in (args.rate, args.painters, args.days, args.hours_per_day)):
        parser.error("rate, painters, days and hours-per-day are required")
    with OperatorCalculationSession(args.workspace) as session:
        if args.status:
            print(json.dumps(list(session.outcomes.values()), sort_keys=True))
            return 0
        request = session.prepare(rate=args.rate, painters=args.painters, days=args.days,
                                  hours_per_day=args.hours_per_day)
        grant = session.authorize(request)
        result = session.execute(request, grant)
        print(json.dumps(result, sort_keys=True))
        return 0 if result["verification_status"] == "verified" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, EOFError) as exc:
        print("Calculation stopped: " + str(exc), file=sys.stderr)
        raise SystemExit(2)
