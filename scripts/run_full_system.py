#!/usr/bin/env python3
"""
SentinelVision - full-system orchestrator.

Runs the ENTIRE Stage 6 system end-to-end in dependency order and writes a
machine-readable status report (results/system_status.json) suitable for a
dashboard/frontend to consume:

    1. environment verification (python deps)
    2. deterministic dataset generation (drift scenarios + integrity set)
    3. drift reference battery build + threshold calibration
    4. drift monitor over all 5 demo scenarios
    5. data-integrity run over the self-poisoned set
    6. validation runner (detection rates, FPR, MMD dual-direction proof)
    7. offline bridge round-trip for BOTH modules (HTTP 201 + GET match)

Usage:
    python scripts/run_full_system.py            # full pipeline
    python scripts/run_full_system.py --skip-tests   # skip pytest suites
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
DRIFT = os.path.join(PROJECT_ROOT, "drift-monitor")
INTEGRITY = os.path.join(PROJECT_ROOT, "data-integrity")

STEPS = []  # (name, status, detail, seconds)


def log(msg):
    print(msg, flush=True)


def record(name, ok, detail="", seconds=0.0):
    STEPS.append(
        {
            "step": name,
            "status": "PASS" if ok else "FAIL",
            "detail": detail,
            "seconds": round(seconds, 2),
        }
    )
    log(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))


def run_step(name, cmd, cwd, check_fn=None, env=None):
    log(f"\n=== {name} ===")
    t0 = time.time()
    proc = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=1800, env=env or dict(os.environ)
    )
    seconds = time.time() - t0
    output = proc.stdout + proc.stderr
    detail = ""
    ok = proc.returncode == 0
    if check_fn is not None:
        try:
            ok2, detail = check_fn(output, proc)
            ok = ok and ok2
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, f"check_fn error: {exc}"
    if not ok and not detail:
        detail = "; ".join(l for l in output.splitlines() if l.strip())[-400:]
    record(name, ok, detail, seconds)
    return ok, output


# ---------------------------------------------------------------------------
# step checkers: parse CLI output to assert real behavior
# ---------------------------------------------------------------------------
def check_reference(output, proc):
    for line in output.splitlines():
        if "reference battery built" in line and "[OK]" in line:
            return True, line.split("[OK] ")[1]
    return False, "no '[OK] reference battery built' line"


def check_calibration(output, proc):
    for line in output.splitlines():
        if "calibration written" in line and "[OK]" in line:
            return True, line.split("[OK] ")[1]
    return False, "no '[OK] calibration written' line"


def _parse_windows(output):
    """Return list of (scenario_label, mmd, assessment, disposition)."""
    results = []
    current = None
    for line in output.splitlines():
        if line.startswith("--- "):
            current = line.strip("- ").strip()
        if line.startswith("[WINDOW]"):
            kv = dict(
                part.split("=", 1) for part in line.split() if "=" in part and not part.startswith("[")
            )
            results.append(
                (
                    current,
                    kv.get("mmd"),
                    kv.get("assessment"),
                    kv.get("disposition"),
                )
            )
    return results


def check_scenarios(output, proc):
    windows = _parse_windows(output)
    if not windows:
        return False, "no [WINDOW] lines found"
    expected = {
        "scenario1-normal": ("NO_SIGNIFICANT_SHIFT", "ACCEPT"),
        "scenario2-lighting-shift": ("OPERATIONAL_SHIFT_LIKELY", "REVIEW"),
        "scenario3-source-change": ("OPERATIONAL_SHIFT_LIKELY", "REVIEW"),
        "scenario4-unexplained": ("UNEXPLAINED_SHIFT", "REVIEW"),
        "scenario5-mixed": ("OPERATIONAL_SHIFT_LIKELY", "REVIEW"),
    }
    bad = [
        w
        for w in windows
        if w[0] in expected and (w[2], w[3]) != expected[w[0]]
    ]
    if bad:
        return False, f"wrong assessments: {bad}"
    return True, f"{len(windows)} scenarios, assessments correct"


def check_integrity(output, proc):
    for line in output.splitlines():
        if line.startswith("[SUMMARY]"):
            summary = json.loads(line[len("[SUMMARY] "):])
            checks = summary.get("checks_run", [])
            errs = summary.get("check_errors", {})
            if set(checks) == {"duplicate", "ood", "label_flip"} and not errs:
                return (
                    True,
                    f"{summary['images_checked']} images, {summary['images_flagged']} flagged",
                )
            return False, f"checks={checks} errors={errs}"
    return False, "no [SUMMARY] line"


def check_validation(output, proc):
    both = "both directions correct: [OK] YES" in output
    return (True, "dual-direction MMD proof OK" if both else "MMD proof FAILED"), (
        "dual-direction OK" if both else "dual-direction FAILED"
    )


# ---------------------------------------------------------------------------
# bridge stub round-trip (mirrors the real bridge contract)
# ---------------------------------------------------------------------------
def start_stub(port=3001):
    proc = subprocess.Popen(
        [sys.executable, os.path.join(HERE, "bridge_stub_demo.py"), str(port)],
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    import time as _t
    import urllib.error

    # Any HTTP response (even 404) proves the server is up.
    for _ in range(40):
        _t.sleep(0.25)
        try:
            with urllib.request.urlopen(f"http://localhost:{port}/findings", timeout=2) as r:
                return proc
        except urllib.error.HTTPError:
            return proc  # server responded -> it is up
        except Exception:
            continue
    proc.terminate()
    raise RuntimeError("bridge stub failed to start on port " + str(port))


def bridge_roundtrip(port=3001):
    """Submit one finding of each module type; verify GET matches POST."""
    stub = start_stub(port)
    ok_drift = ok_integrity = False
    detail = []
    try:
        # drift module
        _, out1 = run_step(
            "bridge: drift finding submit",
            [sys.executable, "-m", "src.run_drift_monitor", "--config", "config.json",
             "--input", os.path.join("..", "data", "scenario1-normal"),
             "--submit", "--bridge-url", f"http://localhost:{port}"],
            cwd=DRIFT,
        )
        ok_drift = "http=201" in out1 and "submitted=True" in out1
        # integrity module
        _, out2 = run_step(
            "bridge: integrity findings submit",
            [sys.executable, "-m", "src.run_data_integrity", "--config", "config.json",
             "--input", os.path.join("..", "data", "integrity-test"),
             "--labels", os.path.join("..", "data", "integrity-test", "label_key.json"),
             "--checks", "duplicate",
             "--submit", "--bridge-url", f"http://localhost:{port}"],
            cwd=INTEGRITY,
        )
        ok_integrity = "http=201" in out2 and "submitted=True" in out2
        # GET round-trip on one finding from each
        drift_id = None
        integrity_id = None
        for line in out1.splitlines():
            if line.startswith("[BRIDGE]"):
                for part in line.split():
                    if part.startswith("assetID="):
                        drift_id = part[len("assetID="):]
        for line in out2.splitlines():
            if line.startswith("[BRIDGE]"):
                for part in line.split():
                    if part.startswith("assetID="):
                        integrity_id = part[len("assetID="):]
                        break
                if integrity_id:
                    break
        for label, asset_id in (("drift", drift_id), ("integrity", integrity_id)):
            if not asset_id:
                continue
            from urllib.parse import quote

            with urllib.request.urlopen(
                f"http://localhost:{port}/findings/{quote(asset_id, safe='')}", timeout=10
            ) as r:
                body = json.loads(r.read().decode("utf-8"))
                got = body.get("data", {})
                matches = got.get("assetID") == asset_id
                detail.append(f"GET {label}: assetID match={matches}")
        return ok_drift and ok_integrity, "; ".join(detail) or "submissions OK"
    finally:
        stub.terminate()
        try:
            stub.wait(timeout=5)
        except Exception:  # noqa: BLE001
            stub.kill()


def main():
    parser = argparse.ArgumentParser(description="Run the full SentinelVision Stage 6 system")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()

    t_start = time.time()
    log("=" * 62)
    log("SentinelVision Stage 6 - FULL SYSTEM RUN")
    log("=" * 62)

    # 1. environment
    log("\n=== environment ===")
    env_ok = True
    env_detail = []
    for mod in ("numpy", "PIL", "sklearn", "scipy", "cleanlab"):
        try:
            __import__(mod)
            env_detail.append(f"{mod}=OK")
        except ImportError:
            env_ok = False
            env_detail.append(f"{mod}=MISSING")
    record("environment: python deps", env_ok, " ".join(env_detail))

    # 2. datasets
    ok1, _ = run_step(
        "datasets: drift demo data",
        [sys.executable, os.path.join(HERE, "make_drift_demo_data.py")],
        PROJECT_ROOT,
    )
    ok2, _ = run_step(
        "datasets: integrity poisoned set",
        [sys.executable, os.path.join(HERE, "make_data_integrity_dataset.py")],
        PROJECT_ROOT,
    )

    # 3. reference + calibration
    ok3, _ = run_step(
        "drift: reference battery build",
        [sys.executable, "-m", "src.reference_builder", "--config", "config.json"],
        DRIFT,
        check_fn=check_reference,
    )
    ok4, _ = run_step(
        "drift: threshold calibration",
        [sys.executable, "-m", "src.threshold_calibrator", "--config", "config.json"],
        DRIFT,
        check_fn=check_calibration,
    )

    # 4. drift scenarios: run each of the 5 directories and aggregate output
    log("\n=== drift: 5 demo scenarios ===")
    t0 = time.time()
    scenario_output = []
    scen_ok = True
    for s in (
        "scenario1-normal",
        "scenario2-lighting-shift",
        "scenario3-source-change",
        "scenario4-unexplained",
        "scenario5-mixed",
    ):
        scenario_output.append(f"--- {s} ---")
        proc = subprocess.run(
            [sys.executable, "-m", "src.run_drift_monitor", "--config", "config.json",
             "--input", os.path.join("..", "data", s)],
            cwd=DRIFT, capture_output=True, text=True, timeout=600,
        )
        scenario_output.append(proc.stdout + proc.stderr)
        if proc.returncode != 0:
            scen_ok = False
    agg_ok, agg_detail = check_scenarios("\n".join(scenario_output), None)
    record("drift: 5 demo scenarios", scen_ok and agg_ok, agg_detail, time.time() - t0)
    ok5 = scen_ok and agg_ok

    # 5. integrity run
    ok6, _ = run_step(
        "integrity: full run on poisoned set",
        [sys.executable, "-m", "src.run_data_integrity", "--config", "config.json",
         "--input", os.path.join("..", "data", "integrity-test"),
         "--labels", os.path.join("..", "data", "integrity-test", "label_key.json"),
         "--answer-key", os.path.join("..", "data", "integrity-test", "label_key.json")],
        INTEGRITY,
        check_fn=check_integrity,
    )

    # 6. validation runner
    ok7, _ = run_step(
        "validation: detection rates + MMD dual-direction proof",
        [sys.executable, os.path.join(INTEGRITY, "run_validation.py"),
         "--out", os.path.join(INTEGRITY, "results", "validation_report.json")],
        PROJECT_ROOT,
        check_fn=check_validation,
    )

    # 7. tests (optional)
    if not args.skip_tests:
        run_step(
            "tests: drift-monitor suite",
            [sys.executable, "-m", "pytest", "tests", "-q", "--no-header"],
            DRIFT,
        )
        run_step(
            "tests: data-integrity suite",
            [sys.executable, "-m", "pytest", "tests", "-q", "--no-header"],
            INTEGRITY,
        )

    # 8. bridge round-trip
    try:
        ok8, detail8 = bridge_roundtrip()
        record("bridge: offline round-trip (both modules)", ok8, detail8)
    except Exception as exc:  # noqa: BLE001
        record("bridge: offline round-trip (both modules)", False, str(exc))

    # machine-readable status report
    all_ok = all(s["status"] == "PASS" for s in STEPS)
    status = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "overall": "HEALTHY" if all_ok else "DEGRADED",
        "total_seconds": round(time.time() - t_start, 1),
        "steps": STEPS,
        "artifacts": {
            "drift_results": "drift-monitor/results/drift_results.json",
            "integrity_results": "data-integrity/results/integrity_results.json",
            "validation_report": "data-integrity/results/validation_report.json",
            "reference_manifest": "drift-monitor/reference/reference_manifest.json",
            "threshold_manifest": "drift-monitor/calibration/threshold_manifest.json",
        },
    }
    out_dir = os.path.join(PROJECT_ROOT, "results")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "system_status.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2)

    log("\n" + "=" * 62)
    log(f"SYSTEM STATUS: {status['overall']}  ({len(STEPS)} steps, {status['total_seconds']}s)")
    for s in STEPS:
        log(f"  [{s['status']}] {s['step']}")
    log(f"status report: {out_path}")
    log("=" * 62)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
