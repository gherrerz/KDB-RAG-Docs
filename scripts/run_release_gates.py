"""Run reproducible smoke/full release gates for this repository."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class GateStep:
    """Represent one gate command with pass/fail expectation."""

    name: str
    command: list[str]


def _repo_root() -> Path:
    """Return repository root from current script path."""
    return Path(__file__).resolve().parents[1]


def _run_step(step: GateStep, cwd: Path) -> bool:
    """Execute one gate command and report pass/fail."""
    rendered_command = " ".join(step.command)
    print(f"\\n[RUN ] {step.name}")
    print(f"       {rendered_command}")
    result = subprocess.run(step.command, cwd=str(cwd), check=False)
    if result.returncode == 0:
        print(f"[PASS] {step.name}")
        return True
    print(f"[FAIL] {step.name} (exit={result.returncode})")
    return False


def _preflight_command(
    python_exe: str,
    base_url: str,
    skip_http: bool,
    expect_tdm_enabled: bool,
) -> list[str]:
    """Build preflight command for release contract checks."""
    command = [
        python_exe,
        "scripts/preflight_release.py",
        "--base-url",
        base_url,
    ]
    if skip_http:
        command.append("--skip-http")
    if expect_tdm_enabled:
        command.append("--expect-tdm-enabled")
    return command


def _smoke_pytest_command(python_exe: str) -> list[str]:
    """Return focused smoke regression suite command."""
    return [
        python_exe,
        "-m",
        "pytest",
        "-q",
        "tests/test_api_async_toggle.py",
        "tests/test_ingestion_view.py",
        "tests/test_main_window_ingestion_mode.py",
    ]


def _full_pytest_command(python_exe: str) -> list[str]:
    """Return full regression suite command."""
    return [python_exe, "-m", "pytest", "-q"]


def _benchmark_commands(python_exe: str) -> list[list[str]]:
    """Return release benchmark commands for full gate mode."""
    return [
        [
            python_exe,
            "scripts/run_multihop_benchmark.py",
            "--benchmark-file",
            "docs/benchmarks/complex_queries_release_es.json",
            "--output-json",
            "docs/benchmarks/last_run_release_es.json",
            "--output-md",
            "docs/benchmarks/last_run_release_es.md",
            "--fail-on-threshold",
        ],
        [
            python_exe,
            "scripts/run_multihop_benchmark.py",
            "--benchmark-file",
            "docs/benchmarks/complex_queries_release_gobierno_datos_es.json",
            "--output-json",
            "docs/benchmarks/last_run_release_gobierno_datos_es.json",
            "--output-md",
            "docs/benchmarks/last_run_release_gobierno_datos_es.md",
            "--fail-on-threshold",
        ],
    ]


def _build_steps(args: argparse.Namespace, python_exe: str) -> list[GateStep]:
    """Build ordered gate steps from CLI options."""
    steps: list[GateStep] = []
    steps.append(
        GateStep(
            name="preflight",
            command=_preflight_command(
                python_exe=python_exe,
                base_url=str(args.base_url),
                skip_http=bool(args.skip_http_preflight),
                expect_tdm_enabled=bool(args.expect_tdm_enabled),
            ),
        )
    )
    steps.append(
        GateStep(
            name="smoke-tests",
            command=_smoke_pytest_command(python_exe),
        )
    )

    if str(args.mode) == "full":
        steps.append(
            GateStep(
                name="full-tests",
                command=_full_pytest_command(python_exe),
            )
        )
        if not bool(args.skip_benchmarks):
            for index, command in enumerate(_benchmark_commands(python_exe), 1):
                steps.append(
                    GateStep(
                        name=f"benchmark-{index}",
                        command=command,
                    )
                )

    return steps


def _print_summary(results: Sequence[tuple[GateStep, bool]]) -> None:
    """Print compact final summary for CI and local terminals."""
    print("\\n== Gate Summary ==")
    for step, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {step.name}")


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for release gates orchestration."""
    parser = argparse.ArgumentParser(
        description=(
            "Run release gates in smoke/full mode with stable command sets."
        )
    )
    parser.add_argument(
        "--mode",
        choices=["smoke", "full"],
        default="smoke",
        help="Gate mode to execute (default: %(default)s).",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base API URL used by preflight checks (default: %(default)s).",
    )
    parser.add_argument(
        "--expect-tdm-enabled",
        action="store_true",
        help="Require TDM paths during preflight OpenAPI checks.",
    )
    parser.add_argument(
        "--skip-http-preflight",
        action="store_true",
        help="Run preflight without HTTP/OpenAPI checks.",
    )
    parser.add_argument(
        "--skip-benchmarks",
        action="store_true",
        help="Skip benchmark commands in full mode.",
    )
    return parser


def main() -> int:
    """CLI entrypoint for smoke/full release gates."""
    args = build_parser().parse_args()
    repo_root = _repo_root()
    python_exe = sys.executable

    steps = _build_steps(args=args, python_exe=python_exe)
    results: list[tuple[GateStep, bool]] = []
    for step in steps:
        passed = _run_step(step=step, cwd=repo_root)
        results.append((step, passed))
        if not passed:
            _print_summary(results)
            return 1

    _print_summary(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
