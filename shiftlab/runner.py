"""Subprocess execution, interactive prompting, and result recording.

Deliberately shells out to the pymobiledevice3 CLI instead of importing the
library. Two reasons: the CLI surface is more stable across releases than the
Python API, and the raw stderr from a failed command IS the finding for several
of these checks. The eventual daemon should import the library directly.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
ARTIFACTS = RESULTS / "artifacts"

# Invoke as a module so it resolves inside whatever venv is active,
# regardless of whether the console script landed on PATH.
PMD3 = [sys.executable, "-m", "pymobiledevice3"]

PASS = "pass"
FAIL = "fail"
SKIPPED = "skipped"
INCONCLUSIVE = "inconclusive"


class C:
    """ANSI colors, disabled when not a tty."""

    _on = sys.stdout.isatty()

    @staticmethod
    def _w(code: str, s: str) -> str:
        return f"\033[{code}m{s}\033[0m" if C._on else s

    @staticmethod
    def bold(s):
        return C._w("1", s)

    @staticmethod
    def dim(s):
        return C._w("2", s)

    @staticmethod
    def cyan(s):
        return C._w("36", s)

    @staticmethod
    def green(s):
        return C._w("32", s)

    @staticmethod
    def red(s):
        return C._w("31", s)

    @staticmethod
    def yellow(s):
        return C._w("33", s)


@dataclass
class Command:
    argv: list
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    @property
    def pretty(self) -> str:
        return " ".join(self.argv)


@dataclass
class CheckResult:
    id: str
    title: str
    question: str
    verdict: str = INCONCLUSIVE
    finding: str = ""
    implication: str = ""
    commands: list = field(default_factory=list)
    observations: dict = field(default_factory=dict)

    def record(self, cmd: Command) -> Command:
        self.commands.append(asdict(cmd))
        return cmd

    def conclude(self, verdict: str, finding: str, implication: str = "") -> "CheckResult":
        self.verdict = verdict
        self.finding = finding
        self.implication = implication
        return self


# --------------------------------------------------------------------------
# process
# --------------------------------------------------------------------------

def run(argv: list, timeout: int = 180, echo: bool = True) -> Command:
    if echo:
        print(C.dim(f"  $ {' '.join(argv)}"))
    try:
        p = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout
        )
        cmd = Command(argv, p.returncode, p.stdout.strip(), p.stderr.strip())
    except subprocess.TimeoutExpired:
        cmd = Command(argv, -1, "", f"timed out after {timeout}s", timed_out=True)
    if echo:
        if cmd.ok:
            print(C.dim("    -> exit 0"))
        else:
            print(C.red(f"    -> exit {cmd.returncode}"))
            for line in (cmd.stderr or cmd.stdout).splitlines()[:6]:
                print(C.red(f"       {line}"))
    return cmd


def try_variants(variants: Iterable[list], timeout: int = 180) -> tuple[Optional[Command], list]:
    """Run candidate argv forms until one exits 0.

    pymobiledevice3 moves subcommands and flag placement between releases, so
    every check probes a few spellings rather than hard-coding one.
    Returns (winning_command_or_None, all_attempts).
    """
    attempts = []
    for argv in variants:
        cmd = run(argv, timeout=timeout)
        attempts.append(cmd)
        if cmd.ok:
            return cmd, attempts
    return None, attempts


# --------------------------------------------------------------------------
# prompting
# --------------------------------------------------------------------------

def _prompt(text: str) -> str:
    try:
        return input(text).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit("aborted")


def ask_yes_no(question: str) -> Optional[bool]:
    """y / n / s(kip). Returns True / False / None."""
    while True:
        ans = _prompt(C.cyan(f"  ? {question} [y/n/s] ")).lower()
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        if ans in ("s", "skip", ""):
            return None
        print("    answer y, n, or s to skip")


def ask_text(question: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    ans = _prompt(C.cyan(f"  ? {question}{suffix} "))
    return ans or default


def confirm_typed(phrase: str, warning: str) -> bool:
    print(C.yellow(f"  ! {warning}"))
    ans = _prompt(C.cyan(f"  ? type {phrase!r} to proceed, anything else to skip: "))
    return ans == phrase


def pause(message: str) -> None:
    _prompt(C.cyan(f"  > {message} (press enter) "))


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------

def banner(text: str) -> None:
    print()
    print(C.bold("=" * 72))
    print(C.bold(text))
    print(C.bold("=" * 72))


def header(check_id: str, title: str, question: str) -> None:
    print()
    print(C.bold(f"[{check_id}] {title}"))
    for line in textwrap.wrap(question, 70):
        print(C.dim(f"      {line}"))
    print()


def verdict_line(r: CheckResult) -> str:
    color = {
        PASS: C.green,
        FAIL: C.red,
        SKIPPED: C.dim,
        INCONCLUSIVE: C.yellow,
    }[r.verdict]
    label = r.verdict.upper().ljust(13)
    return f"  {color(label)} {r.title}"


def device_udid(ctx: dict) -> Optional[str]:
    """UDID, cached to disk so checks run with the cable out can still use it.

    pymobiledevice3 needs --udid whenever more than one candidate turns up,
    which is the normal case over Bonjour.
    """
    if ctx.get("udid"):
        return ctx["udid"]
    cache = ARTIFACTS / "udid.txt"
    if cache.exists():
        val = cache.read_text().strip()
        if val:
            ctx["udid"] = val
            return val
    probe = run(PMD3 + ["lockdown", "info"], timeout=60, echo=False)
    if probe.ok:
        for line in probe.stdout.splitlines():
            if "UniqueDeviceID" in line:
                val = line.split(":", 1)[1].strip().strip('",')
                ARTIFACTS.mkdir(parents=True, exist_ok=True)
                cache.write_text(val + "\n")
                ctx["udid"] = val
                return val
    return None


def preflight() -> list:
    """Things that will waste your time if they are wrong."""
    problems = []
    if sys.version_info < (3, 10):
        problems.append(f"python {sys.version_info.major}.{sys.version_info.minor} found, need 3.10+")
    probe = run(PMD3 + ["version"], timeout=60, echo=False)
    if not probe.ok:
        probe = run(PMD3 + ["--help"], timeout=60, echo=False)
    if not probe.ok:
        problems.append("pymobiledevice3 not importable: pip install pymobiledevice3")
    if shutil.which("idevice_id") is None:
        # not fatal, just useful to know
        pass
    return problems


# --------------------------------------------------------------------------
# persistence
# --------------------------------------------------------------------------

def save(results: list, phase: str) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RESULTS / f"run-{phase}-{stamp}.json"
    path.write_text(
        json.dumps(
            {
                "phase": phase,
                "timestamp": stamp,
                "python": sys.version,
                "results": [asdict(r) for r in results],
            },
            indent=2,
        )
    )
    write_report(results, phase, stamp)
    return path


def write_report(results: list, phase: str, stamp: str) -> Path:
    path = RESULTS / f"REPORT-{phase}.md"
    lines = [
        f"# ShiftLab phase {phase} report",
        "",
        f"Run: {stamp}",
        "",
        "| Check | Verdict | Finding |",
        "| --- | --- | --- |",
    ]
    for r in results:
        finding = r.finding.replace("|", "\\|") or "-"
        lines.append(f"| {r.id} {r.title} | {r.verdict} | {finding} |")
    lines += ["", "## Detail", ""]
    for r in results:
        lines += [
            f"### [{r.id}] {r.title}",
            "",
            f"**Question.** {r.question}",
            "",
            f"**Verdict.** {r.verdict}",
            "",
            f"**Finding.** {r.finding or '-'}",
            "",
        ]
        if r.implication:
            lines += [f"**So what.** {r.implication}", ""]
        if r.observations:
            lines += ["**Observed on device.**", ""]
            for k, v in r.observations.items():
                lines.append(f"- {k}: `{v}`")
            lines.append("")
        if r.commands:
            lines += ["<details><summary>commands</summary>", "", "```"]
            for c in r.commands:
                lines.append("$ " + " ".join(c["argv"]))
                lines.append(f"exit {c['returncode']}")
                out = (c["stderr"] or c["stdout"]).strip()
                if out:
                    for line in out.splitlines()[:12]:
                        lines.append("  " + line)
                lines.append("")
            lines += ["```", "", "</details>", ""]
    path.write_text("\n".join(lines))
    return path
