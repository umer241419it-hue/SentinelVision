"""Tests for the CLI runner and the Stage 6 validation runner."""

import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_INTEGRITY_ROOT = os.path.dirname(HERE)
PROJECT_ROOT = os.path.dirname(DATA_INTEGRITY_ROOT)


@pytest.fixture(scope="module")
def cli_run(poisoned_dataset, tmp_path_factory):
    """Run the CLI once against the poisoned dataset with a temp cache."""
    base = tmp_path_factory.mktemp("cli_base")
    out = os.path.join(base, "out")
    env = dict(os.environ)
    cmd = [
        sys.executable, "-m", "src.run_data_integrity",
        "--config", os.path.join(DATA_INTEGRITY_ROOT, "config.json"),
        "--input", poisoned_dataset["dir"],
        "--labels", os.path.join(poisoned_dataset["dir"], "label_key.json"),
        "--answer-key", os.path.join(poisoned_dataset["dir"], "label_key.json"),
        "--timestamp-fixed", "2026-01-01T00:00:00Z",
    ]
    # The CLI writes into the config-relative base dir; run from a copy of
    # the module config with output redirected via env is overkill - instead
    # run it with cwd=data-integrity and accept it writes results/ there.
    proc = subprocess.run(
        cmd, cwd=DATA_INTEGRITY_ROOT, env=env, capture_output=True, text=True, timeout=600,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    with open(os.path.join(DATA_INTEGRITY_ROOT, "results", "integrity_results.json"), "r", encoding="utf-8") as f:
        results = json.load(f)
    return results, proc


def test_cli_produces_results_and_evidence(cli_run):
    results, proc = cli_run
    assert results["run"]["module"] == "DataIntegrity"
    assert results["summary"]["images_checked"] == 120
    assert results["summary"]["images_flagged"] > 0
    for entry in results["results"][:3]:
        f = entry["finding"]
        assert set(f.keys()) == {
            "assetID", "moduleName", "reason", "evidenceHash",
            "confidence", "severity", "disposition", "timestamp",
        }
        assert os.path.isfile(os.path.join(DATA_INTEGRITY_ROOT, entry["evidence_path"]))


def test_cli_findings_are_unique_asset_ids(cli_run):
    results, _ = cli_run
    ids = [e["finding"]["assetID"] for e in results["results"]]
    assert len(ids) == len(set(ids))


def test_validation_runner_dual_direction(poisoned_dataset, tmp_path):
    """The Stage 6 validation runner must prove both MMD directions."""
    out = os.path.join(str(tmp_path), "validation_report.json")
    cmd = [
        sys.executable, os.path.join(DATA_INTEGRITY_ROOT, "run_validation.py"),
        "--integrity-dir", poisoned_dataset["dir"],
        "--labels", os.path.join(poisoned_dataset["dir"], "label_key.json"),
        "--out", out,
    ]
    proc = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=900)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    with open(out, "r", encoding="utf-8") as f:
        report = json.load(f)
    assert report["shift_proof"]["both_directions_correct"] is True
    assert report["integrity"]["overall"]["detection_rate"] is not None


@pytest.mark.live
def test_bridge_roundtrip_live(poisoned_dataset):
    """Opt-in live test (SENTINELVISION_LIVE_BRIDGE=1): submit one finding."""
    if os.environ.get("SENTINELVISION_LIVE_BRIDGE") != "1":
        pytest.skip("live bridge test disabled (set SENTINELVISION_LIVE_BRIDGE=1)")
    with open(os.path.join(DATA_INTEGRITY_ROOT, "results", "integrity_results.json"), "r", encoding="utf-8") as f:
        results = json.load(f)
    assert results["results"], "no findings available; run the CLI first"
    sys.path.insert(0, DATA_INTEGRITY_ROOT)
    from src.bridge_client import submit_finding

    finding = results["results"][0]["finding"]
    report = submit_finding(finding, os.environ.get("BRIDGE_URL", "http://localhost:3000"))
    assert report["submitted"] is True, report
    assert report["ledger_verification"], report
