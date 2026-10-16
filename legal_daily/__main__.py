import os
import sys

from .daily import run_daily
from .incoming import run_message
from .research import run_research


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    force = "--force" in sys.argv or os.environ.get("FORCE_DAILY") == "true" or os.environ.get("FORCE_RESEARCH") == "true"
    if command == "daily":
        run_daily(force=force)
        return
    if command == "message":
        run_message()
        return
    if command == "research":
        mode = "weekly" if "--weekly" in sys.argv or os.environ.get("RESEARCH_MODE") == "weekly" else "daily"
        run_research(mode=mode, force=force)
        return
    print("用法: python -m legal_daily daily|message|research")
    sys.exit(2)


if __name__ == "__main__":
    main()
