"""Run rollout preflight checks for legacy and TDM API compatibility."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List


LEGACY_PATHS = {
    "/health",
    "/readiness",
    "/sources/ingest",
    "/sources/ingest/async",
    "/sources/reset",
    "/jobs/{job_id}",
    "/query",
    "/query/retrieval",
}
TDM_PATHS = {
    "/tdm/ingest",
    "/tdm/query",
    "/tdm/catalog/services/{service_name}",
    "/tdm/catalog/tables/{table_name}",
    "/tdm/virtualization/preview",
    "/tdm/synthetic/profile/{table_name}",
}


@dataclass(frozen=True)
class CheckResult:
    """Result of one preflight check with pass/fail information."""

    name: str
    passed: bool
    details: str


def _repo_root() -> Path:
    """Return repository root derived from script location."""
    return Path(__file__).resolve().parents[1]


def _env_flag(name: str, default: bool = False) -> bool:
    """Parse boolean environment flags from common truthy values."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _flag_checks() -> List[CheckResult]:
    """Validate TDM feature flag dependencies before rollout checks."""
    checks: List[CheckResult] = []

    enable_tdm = _env_flag("ENABLE_TDM", False)
    enable_masking = _env_flag("TDM_ENABLE_MASKING", False)
    enable_virtualization = _env_flag("TDM_ENABLE_VIRTUALIZATION", False)
    enable_synthetic = _env_flag("TDM_ENABLE_SYNTHETIC", False)

    checks.append(
        CheckResult(
            name="flags:base",
            passed=True,
            details=(
                f"ENABLE_TDM={enable_tdm} "
                f"MASKING={enable_masking} "
                f"VIRTUALIZATION={enable_virtualization} "
                f"SYNTHETIC={enable_synthetic}"
            ),
        )
    )

    if not enable_tdm and (
        enable_masking or enable_virtualization or enable_synthetic
    ):
        checks.append(
            CheckResult(
                name="flags:dependency",
                passed=False,
                details=(
                    "TDM capability flags require ENABLE_TDM=true."
                ),
            )
        )
    else:
        checks.append(
            CheckResult(
                name="flags:dependency",
                passed=True,
                details="Feature flag dependencies are consistent.",
            )
        )

    return checks


def _http_get_json(url: str, timeout_sec: float) -> Dict[str, object]:
    """Fetch JSON payload from URL using urllib with explicit timeout."""
    request = urllib.request.Request(url=url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout_sec) as response:
        payload = response.read().decode("utf-8")
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected JSON object from {url}")
    return parsed


def evaluate_openapi_paths(
    discovered_paths: Iterable[str],
    expect_tdm_enabled: bool,
) -> List[CheckResult]:
    """Evaluate OpenAPI path set for legacy and TDM contract expectations."""
    path_set = {str(path) for path in discovered_paths}
    checks: List[CheckResult] = []

    missing_legacy = sorted(path for path in LEGACY_PATHS if path not in path_set)
    checks.append(
        CheckResult(
            name="openapi:legacy_paths",
            passed=not missing_legacy,
            details=(
                "All legacy paths are present."
                if not missing_legacy
                else f"Missing legacy paths: {', '.join(missing_legacy)}"
            ),
        )
    )

    missing_tdm = sorted(path for path in TDM_PATHS if path not in path_set)
    if expect_tdm_enabled:
        checks.append(
            CheckResult(
                name="openapi:tdm_paths",
                passed=not missing_tdm,
                details=(
                    "All TDM paths are present."
                    if not missing_tdm
                    else f"Missing TDM paths: {', '.join(missing_tdm)}"
                ),
            )
        )
    else:
        checks.append(
            CheckResult(
                name="openapi:tdm_paths",
                passed=True,
                details=(
                    "TDM paths found and tolerated (runtime gating via 404)."
                    if len(missing_tdm) < len(TDM_PATHS)
                    else "TDM paths not exposed in OpenAPI."
                ),
            )
        )

    return checks


def _http_checks(
    base_url: str,
    timeout_sec: float,
    expect_tdm_enabled: bool,
) -> List[CheckResult]:
    """Run HTTP preflight against live API endpoint and OpenAPI contract."""
    checks: List[CheckResult] = []

    try:
        health = _http_get_json(f"{base_url}/health", timeout_sec)
        checks.append(
            CheckResult(
                name="http:health",
                passed=health.get("status") == "ok",
                details=f"health={health}",
            )
        )
    except (urllib.error.URLError, ValueError, json.JSONDecodeError) as exc:
        checks.append(
            CheckResult(
                name="http:health",
                passed=False,
                details=f"Health check failed: {exc}",
            )
        )
        return checks

    try:
        openapi = _http_get_json(f"{base_url}/openapi.json", timeout_sec)
        paths = openapi.get("paths", {})
        if not isinstance(paths, dict):
            raise ValueError("OpenAPI 'paths' field is not an object.")
        checks.extend(
            evaluate_openapi_paths(
                discovered_paths=paths.keys(),
                expect_tdm_enabled=expect_tdm_enabled,
            )
        )
    except (urllib.error.URLError, ValueError, json.JSONDecodeError) as exc:
        checks.append(
            CheckResult(
                name="http:openapi",
                passed=False,
                details=f"OpenAPI check failed: {exc}",
            )
        )

    return checks


def _print_results(results: List[CheckResult]) -> None:
    """Render check results in a CI-friendly line-oriented format."""
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.name}: {result.details}")


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for release preflight options."""
    parser = argparse.ArgumentParser(
        description=(
            "Run release preflight checks for legacy compatibility and "
            "TDM rollout readiness."
        )
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base API URL used for HTTP checks (default: %(default)s).",
    )
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=5.0,
        help="HTTP timeout in seconds (default: %(default)s).",
    )
    parser.add_argument(
        "--expect-tdm-enabled",
        action="store_true",
        help="Require TDM endpoints in OpenAPI path checks.",
    )
    parser.add_argument(
        "--skip-http",
        action="store_true",
        help="Run only local flag dependency checks.",
    )
    return parser


def main() -> int:
    """CLI entrypoint for rollout preflight script."""
    parser = build_parser()
    args = parser.parse_args()

    os.chdir(_repo_root())

    results = _flag_checks()
    if not args.skip_http:
        results.extend(
            _http_checks(
                base_url=str(args.base_url).rstrip("/"),
                timeout_sec=max(0.1, float(args.timeout_sec)),
                expect_tdm_enabled=bool(args.expect_tdm_enabled),
            )
        )

    _print_results(results)

    failed = [result for result in results if not result.passed]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
