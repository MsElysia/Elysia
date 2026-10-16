"""Entry point for python -m elysia."""
import sys

from elysia_offline import main
raise SystemExit(main(sys.argv[1:]))
