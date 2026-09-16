"""ShiftLab entry point.

  python -m shiftlab              run phase 1
  python -m shiftlab --phase 2    run phase 2 (after supervising)
  python -m shiftlab --only 05    run one check
  python -m shiftlab --no-cleanup leave test profiles installed
"""
from __future__ import annotations

import argparse
import sys

from . import checks, phase2
from .runner import C, banner, preflight, save, verdict_line


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="shiftlab", description=__doc__)
    ap.add_argument("--phase", choices=["1", "2"], default="1")
    ap.add_argument("--only", metavar="ID", help="run a single check, e.g. 05")
    ap.add_argument("--no-cleanup", action="store_true")
    args = ap.parse_args(argv)

    banner(f"ShiftLab  phase {args.phase}")
    print("Answers the questions that decide the architecture, before you")
    print("erase anything. Nothing in phase 1 is irreversible except check 03,")
    print("which is gated behind a typed confirmation.")

    problems = preflight()
    if problems:
        print()
        for p in problems:
            print(C.red(f"  ! {p}"))
        return 2

    suite = checks.PHASE1 if args.phase == "1" else phase2.PHASE2
    if args.only:
        suite = [f for f in suite if f"check_{args.only}" in f.__name__]
        if not suite:
            print(C.red(f"  ! no check {args.only} in phase {args.phase}"))
            return 2

    ctx: dict = {}
    results = []
    try:
        # Several checks validate input against the app inventory. Running one
        # check on its own would otherwise skip that and lose the guard.
        if args.only and args.phase == "1" and args.only not in ("01", "02"):
            print(C.dim("  (populating app inventory first so id guards work)"))
            checks.check_02_inventory(ctx)
        for fn in suite:
            results.append(fn(ctx))
    except SystemExit:
        print(C.yellow("\n  aborted, saving what we have"))
    finally:
        if args.phase == "1" and not args.no_cleanup and not args.only:
            checks.cleanup(ctx)

    banner("results")
    for r in results:
        print(verdict_line(r))
    path = save(results, args.phase)
    print()
    print(f"  json   {path}")
    print(f"  report {path.parent / ('REPORT-' + args.phase + '.md')}")

    decisive = next((r for r in results if r.id == "05"), None)
    if decisive and decisive.verdict in ("pass", "fail"):
        print()
        print(C.bold("  decision:"))
        print(f"  {decisive.implication}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
