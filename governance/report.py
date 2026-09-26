"""
SentinelVision - Assurance Report Generator & Cryptographic Signer.

Generates machine-readable JSON (with tamper-evident Ed25519 report signing),
comprehensive GitHub Markdown, and interactive modern HTML analyst reports.
"""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CRYPTO_UTILS_DIR = os.path.join(WORKSPACE_ROOT, "crypto-utils")
if CRYPTO_UTILS_DIR not in sys.path:
    sys.path.insert(0, CRYPTO_UTILS_DIR)

from .schema import AssuranceReport, FindingCategory, FindingStatus, GovernanceDisposition, SeverityLevel

try:
    from canonical import canonical_json
    from sign import sign_fields
except ImportError:
    def canonical_json(obj: Dict[str, Any]) -> str:
        return json.dumps(obj, sort_keys=True, separators=(",", ":"))
    sign_fields = None


class AssuranceReportGenerator:
    """
    Compiles, cryptographically signs, and renders multi-format assurance reports.
    """

    def __init__(self, output_dir: Union[str, Path]):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        report: AssuranceReport,
        sign_report: bool = True,
    ) -> Tuple[Path, Path, Path]:
        """
        Generate and persist:
        1. assurance_report.json (machine-readable, signed)
        2. assurance_report.md (analyst markdown)
        3. assurance_report.html (interactive analyst dashboard)

        Returns (json_path, md_path, html_path).
        """
        report_dict = report.to_dict()

        # 1. Cryptographic Report Hashing & Signing
        if sign_report:
            payload_to_hash = {k: v for k, v in report_dict.items() if k != "report_integrity"}
            canonical_str = canonical_json(payload_to_hash)
            report_hash = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

            signature = None
            if sign_fields:
                try:
                    signature = sign_fields("GovernanceEngine", payload_to_hash)
                except Exception as e:
                    # Fallback if key is missing in custom test environments
                    signature = f"UNSIGNED_TEST_KEY_FALLBACK:{e}"

            report_dict["report_integrity"] = {
                "report_hash": report_hash,
                "signature": signature,
                "signer": "GovernanceEngine",
                "algorithm": "Ed25519+SHA256",
                "signed_at": datetime.now(timezone.utc).isoformat(),
            }
            report.report_integrity = report_dict["report_integrity"]

        # 2. Write JSON Report
        json_path = self.output_dir / "assurance_report.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report_dict, f, indent=2)

        # 3. Write Markdown Report
        md_content = self.render_markdown(report_dict)
        md_path = self.output_dir / "assurance_report.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        # 4. Write HTML Report
        html_content = self.render_html(report_dict)
        html_path = self.output_dir / "assurance_report.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        return json_path, md_path, html_path

    # --------------------------------------------------------------------------
    # Markdown Rendering
    # --------------------------------------------------------------------------

    def render_markdown(self, r: Dict[str, Any]) -> str:
        lines: List[str] = []
        asmt_id = r.get("assessment_id", "N/A")
        oa = r.get("overall_assessment", {})
        status = oa.get("overall_status", "UNKNOWN")
        disp = oa.get("disposition", "UNKNOWN")
        sys_info = r.get("system", {})
        integrity = r.get("report_integrity", {})

        lines.append(f"# SentinelVision Assurance Report — `{asmt_id}`\n")
        lines.append("> **SIH PS 26228**: Trustworthy Computer Vision Integrity Assurance for Data, Models and Inference Outputs in Multi-Contributor Pipelines\n")

        # Section 1: Executive Summary
        lines.append("## 1. Executive Summary\n")
        lines.append(f"- **Overall Assessment Status**: `{status}`")
        lines.append(f"- **Recommended Governance Disposition**: **`{disp}`**")
        lines.append(f"- **Assessment Summary**: {oa.get('summary', '')}")
        lines.append(f"- **Assessment ID**: `{asmt_id}`")
        lines.append(f"- **Assessment Timestamp**: `{r.get('assessment_timestamp')}`")
        lines.append(f"- **Execution Mode**: `{sys_info.get('environment', 'offline/air-gapped')}` (100% Offline / Non-Networked)\n")

        lines.append("| Metric | Count |")
        lines.append("| :--- | :---: |")
        lines.append(f"| Critical / Quarantine Findings | **{oa.get('critical_findings', 0)}** |")
        lines.append(f"| Review / Warning Findings | {oa.get('review_findings', 0) + oa.get('warning_findings', 0)} |")
        lines.append(f"| Passed / Acceptable Checks | {oa.get('pass_findings', 0)} |")
        lines.append(f"| Unassessed / Inaccessible Checks | {oa.get('not_assessed', 0)} |\n")

        if oa.get("basis"):
            lines.append("### Assessment Basis")
            for b in oa["basis"]:
                lines.append(f"- {b}")
            lines.append("")

        # Section 2: Assessment Scope & Asset Inventory
        lines.append("## 2. Assessment Scope & Asset Inventory\n")
        assets = r.get("assets", {})
        lines.append(f"- **Evaluated Datasets**: {len(assets.get('datasets', []))}")
        for ds in assets.get("datasets", []):
            lines.append(f"  - `{ds.get('asset_id')}`: {ds.get('name')} ({ds.get('sample_count', 0):,} samples)")

        lines.append(f"- **Evaluated Models**: {len(assets.get('models', []))}")
        for m in assets.get("models", []):
            lines.append(f"  - `{m.get('asset_id')}`: Architecture `{m.get('architecture')}`, Digest `sha256:{m.get('digest', '')[:16]}...` (Access: `{m.get('access_level')}`)")

        lines.append(f"- **Verified Inference Records**: {len(assets.get('inference_records', []))}")
        lines.append(f"- **Monitored Reference Batteries**: {len(assets.get('reference_batteries', []))}\n")

        # Section 3: Access Profile & Assumptions
        lines.append("## 3. Access Profile & Operational Assumptions\n")
        ap = r.get("access_profile", {})
        lines.append("| Dimension | Declared Access | Notes |")
        lines.append("| :--- | :--- | :--- |")
        lines.append(f"| **Data Access** | `{ap.get('data_access', 'LOCAL_FILESYSTEM')}` | Local filesystem batch ingestion |")
        lines.append(f"| **Model Access** | `{ap.get('model_access', 'WHITE_BOX')}` | White-box weights (.pt) required for inversion |")
        lines.append(f"| **Inference Access** | `{ap.get('inference_access', 'SEALED_RECORDS')}` | Immutable 9-field cryptographic seals |")
        lines.append(f"| **Drift Monitoring** | `{ap.get('drift_access', 'REFERENCE_BATTERY')}` | Frozen reference battery & rolling live windows |\n")

        # Section 4: Integrity Checks Executed
        lines.append("## 4. Integrity Checks Executed\n")
        lines.append("| Check ID | Module | Capability / Check Name | Status | Timestamp |")
        lines.append("| :--- | :--- | :--- | :---: | :--- |")
        for chk in r.get("checks", []):
            lines.append(f"| `{chk.get('check_id')}` | `{chk.get('module')}` | {chk.get('name')} | `{chk.get('execution_status')}` | {chk.get('timestamp')[:19]} |")
        lines.append("")

        # Section 5: Findings & Evidence
        lines.append("## 5. Governance Findings & Supporting Evidence\n")
        findings = r.get("findings", [])
        if not findings:
            lines.append("No findings generated during this run.\n")
        else:
            for f in findings:
                fid = f.get("finding_id")
                cat = f.get("category")
                sev = f.get("severity")
                fst = f.get("status")
                conf = f.get("confidence", {})
                rec = f.get("recommendation", {})
                lines.append(f"### Finding `{fid}`: {f.get('title')}\n")
                lines.append(f"- **Category**: `{cat}` | **Status**: `{fst}` | **Severity**: **`{sev}`** | **Confidence**: `{conf.get('interpretation')} ({conf.get('value')})`")
                lines.append(f"- **Affected Scope**: `{f.get('affected_scope')}`")
                lines.append(f"- **Detection Method**: {f.get('detection_method')}")
                lines.append(f"- **Description**: {f.get('description')}")
                lines.append(f"- **Recommended Disposition**: **`{rec.get('disposition')}`** (Priority: `{rec.get('priority')}`)")
                lines.append(f"- **Suggested Action**: {rec.get('suggested_action')}\n")

                if f.get("evidence"):
                    lines.append("**Supporting Evidence Items:**")
                    for ev in f["evidence"]:
                        lines.append(f"  - `[{ev.get('type')}]` Ref: `{ev.get('reference')}`" + (f" | Metric: `{ev.get('metric')}`={ev.get('value')} (Threshold: {ev.get('threshold')})" if ev.get('metric') else ""))
                    lines.append("")

                if f.get("limitations"):
                    lines.append("**Known Limitations:**")
                    for lim in f["limitations"]:
                        lines.append(f"  - {lim}")
                    lines.append("")

        # Section 6: Coverage Matrix
        lines.append("## 6. Coverage Statement & Threat Matrix\n")
        cov = r.get("coverage", {})
        lines.append("### 6.1 Attack-Class Declarations")
        lines.append("| Threat / Attack Class | Platform Support Status | Detection Method | Required Access |")
        lines.append("| :--- | :---: | :--- | :--- |")
        for atk in cov.get("attack_classes", []):
            lines.append(f"| **{atk.get('attack_class')}** | `{atk.get('support_status')}` | {atk.get('detection_method')} | {atk.get('required_access')} |")
        lines.append("")

        # Section 7: System Limitations
        lines.append("## 7. Concrete System Limitations\n")
        for lim in r.get("limitations", []):
            lines.append(f"- {lim}")
        lines.append("")

        # Section 8: Analyst Recommendations
        lines.append("## 8. Actionable Analyst Recommendations\n")
        recs = r.get("recommendations", [])
        if not recs:
            lines.append("No corrective actions required. All checks cleared.\n")
        else:
            lines.append("| Finding Ref | Asset ID | Recommended Disposition | Priority | Action Guidance |")
            lines.append("| :--- | :--- | :---: | :---: | :--- |")
            for rec in recs:
                lines.append(f"| `{rec.get('finding_id')}` | `{rec.get('asset_id')}` | **`{rec.get('disposition')}`** | `{rec.get('priority')}` | {rec.get('suggested_action')} |")
            lines.append("")

        # Section 9: Audit Trail Summary
        lines.append("## 9. Tamper-Evident Audit Trail\n")
        audit = r.get("audit", {})
        lines.append(f"- **Chain Verification**: `{audit.get('verification_status', 'VALID')}`")
        lines.append(f"- **Recorded Events**: {audit.get('event_count', 0)}")
        lines.append(f"- **Genesis Previous Hash**: `{audit.get('genesis_hash', '')[:24]}...`")
        lines.append(f"- **Terminal Chain Hash**: `{audit.get('final_chain_hash', '')}`\n")
        lines.append("| Seq | Event Type | Timestamp | Reference IDs | Event Hash (SHA-256) |")
        lines.append("| :---: | :--- | :--- | :--- | :--- |")
        for ev in audit.get("events", [])[:15]:
            refs = ", ".join(ev.get("reference_ids", [])) or "N/A"
            lines.append(f"| {ev.get('sequence_index')} | `{ev.get('event_type')}` | {ev.get('timestamp')[:19]} | {refs[:25]} | `{ev.get('event_hash', '')[:16]}...` |")
        lines.append("")

        # Section 10: Cryptographic Report Binding & Reproducibility
        lines.append("## 10. Report Integrity & Reproducibility\n")
        lines.append(f"- **Report Hash (SHA-256)**: `{integrity.get('report_hash', 'N/A')}`")
        lines.append(f"- **Signer Module**: `{integrity.get('signer', 'GovernanceEngine')}`")
        lines.append(f"- **Ed25519 Signature**: `{integrity.get('signature', 'N/A')}`")
        lines.append(f"- **Algorithm**: `{integrity.get('algorithm', 'Ed25519+SHA256')}`")
        lines.append(f"- **Signed At**: `{integrity.get('signed_at', 'N/A')}`\n")

        repro = r.get("reproducibility", {})
        lines.append(f"```text\nPlatform: {repro.get('platform')}\nPython:   {repro.get('python_version')}\nOffline:  {repro.get('offline_mode')}\n```\n")

        return "\n".join(lines)

    # --------------------------------------------------------------------------
    # HTML Rendering
    # --------------------------------------------------------------------------

    def render_html(self, r: Dict[str, Any]) -> str:
        asmt_id = r.get("assessment_id", "N/A")
        oa = r.get("overall_assessment", {})
        status = oa.get("overall_status", "UNKNOWN")
        disp = oa.get("disposition", "UNKNOWN")
        integrity = r.get("report_integrity", {})

        status_color = "#10b981" if status == "PASS" else ("#f59e0b" if "REVIEW" in status or "LIMITATIONS" in status else "#ef4444")
        disp_bg = "#ecfdf5" if disp == "ACCEPT" else ("#fffbeb" if disp == "REVIEW" else "#fef2f2")
        disp_border = "#059669" if disp == "ACCEPT" else ("#d97706" if disp == "REVIEW" else "#dc2626")
        disp_text = "#065f46" if disp == "ACCEPT" else ("#92400e" if disp == "REVIEW" else "#991b1b")

        findings_json_str = json.dumps(r.get("findings", []), indent=2).replace("<", "&lt;").replace(">", "&gt;")

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SentinelVision Assurance Report — {asmt_id}</title>
  <style>
    :root {{
      --bg: #0f172a;
      --card-bg: #1e293b;
      --card-border: #334155;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --accent: #38bdf8;
      --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }}
    body {{
      margin: 0;
      padding: 2rem;
      background-color: var(--bg);
      color: var(--text);
      font-family: var(--font);
      line-height: 1.6;
    }}
    .container {{
      max-width: 1200px;
      margin: 0 auto;
    }}
    header {{
      border-bottom: 1px solid var(--card-border);
      padding-bottom: 1.5rem;
      margin-bottom: 2rem;
    }}
    h1, h2, h3 {{ color: var(--text); font-weight: 700; }}
    .badge {{
      display: inline-block;
      padding: 0.25rem 0.75rem;
      border-radius: 9999px;
      font-weight: 700;
      font-size: 0.85rem;
      letter-spacing: 0.05em;
    }}
    .status-badge {{
      background: {status_color};
      color: #ffffff;
    }}
    .disposition-card {{
      background: {disp_bg};
      border-left: 6px solid {disp_border};
      color: {disp_text};
      padding: 1.25rem;
      border-radius: 0.5rem;
      margin: 1.5rem 0;
    }}
    .grid-4 {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 1rem;
      margin: 1.5rem 0;
    }}
    .stat-card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 0.5rem;
      padding: 1.25rem;
      text-align: center;
    }}
    .stat-val {{ font-size: 2rem; font-weight: 800; color: var(--accent); }}
    .stat-lbl {{ font-size: 0.85rem; color: var(--text-muted); text-transform: uppercase; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 1rem 0;
      background: var(--card-bg);
      border-radius: 0.5rem;
      overflow: hidden;
    }}
    th, td {{
      padding: 0.75rem 1rem;
      border-bottom: 1px solid var(--card-border);
      text-align: left;
    }}
    th {{ background: #1e293b; color: var(--text-muted); font-size: 0.85rem; text-transform: uppercase; }}
    .finding-card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 0.5rem;
      padding: 1.25rem;
      margin-bottom: 1rem;
    }}
    .evidence-box {{
      background: #0b1120;
      border: 1px solid #1e293b;
      padding: 0.75rem;
      border-radius: 0.375rem;
      font-family: monospace;
      font-size: 0.85rem;
      color: #38bdf8;
      overflow-x: auto;
    }}
    .crypto-verify {{
      background: #111827;
      border: 1px dashed #374151;
      padding: 1rem;
      border-radius: 0.5rem;
      font-family: monospace;
      font-size: 0.85rem;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <div>
          <h1 style="margin:0;">SentinelVision Assurance Report</h1>
          <p style="margin:0.25rem 0 0; color:var(--text-muted);">Trustworthy Computer Vision Integrity Assurance (SIH PS 26228)</p>
        </div>
        <div>
          <span class="badge status-badge">{status}</span>
        </div>
      </div>
      <p style="color:var(--text-muted); font-size:0.9rem; margin-top:0.75rem;">
        Assessment ID: <code>{asmt_id}</code> | Timestamp: {r.get('assessment_timestamp')} | Mode: <strong>100% Offline Air-Gapped</strong>
      </p>
    </header>

    <div class="disposition-card">
      <h2 style="margin:0 0 0.5rem; color:{disp_text};">Governance Disposition: {disp}</h2>
      <p style="margin:0; font-size:1.05rem;">{oa.get('summary')}</p>
    </div>

    <div class="grid-4">
      <div class="stat-card">
        <div class="stat-val" style="color:#ef4444;">{oa.get('critical_findings', 0)}</div>
        <div class="stat-lbl">Critical / Quarantine</div>
      </div>
      <div class="stat-card">
        <div class="stat-val" style="color:#f59e0b;">{oa.get('review_findings', 0) + oa.get('warning_findings', 0)}</div>
        <div class="stat-lbl">Review / Warning</div>
      </div>
      <div class="stat-card">
        <div class="stat-val" style="color:#10b981;">{oa.get('pass_findings', 0)}</div>
        <div class="stat-lbl">Checks Passed</div>
      </div>
      <div class="stat-card">
        <div class="stat-val" style="color:#94a3b8;">{oa.get('not_assessed', 0)}</div>
        <div class="stat-lbl">Unassessed</div>
      </div>
    </div>

    <h2>Assessment Basis</h2>
    <ul>
      {"".join(f"<li>{b}</li>" for b in oa.get('basis', []))}
    </ul>

    <h2>Findings & Corroborated Evidence ({len(r.get('findings', []))})</h2>
    {"".join(f'''
    <div class="finding-card">
      <div style="display:flex; justify-content:space-between; align-items:flex-start;">
        <div>
          <h3 style="margin:0 0 0.25rem;">{f.get('title')}</h3>
          <span style="font-size:0.8rem; color:var(--text-muted);">Asset: <code>{f.get('asset_id')}</code> | Method: {f.get('detection_method')}</span>
        </div>
        <div>
          <span class="badge" style="background:#334155; color:#f8fafc;">{f.get('status')}</span>
          <span class="badge" style="background:{'#ef4444' if f.get('severity')=='CRITICAL' else ('#f59e0b' if f.get('severity') in ('HIGH','MEDIUM') else '#10b981')}; color:#fff;">{f.get('severity')}</span>
        </div>
      </div>
      <p style="margin:0.75rem 0;">{f.get('description')}</p>
      <div style="background:#0f172a; padding:0.75rem; border-radius:0.375rem; border-left:4px solid var(--accent); margin-bottom:0.75rem;">
        <strong>Recommended Analyst Action ({f.get('recommendation', {}).get('disposition')}):</strong> {f.get('recommendation', {}).get('suggested_action')}
      </div>
      <details>
        <summary style="cursor:pointer; color:var(--accent);">View Supporting Evidence ({len(f.get('evidence', []))} items)</summary>
        <div class="evidence-box" style="margin-top:0.5rem;">
          <pre style="margin:0;">{json.dumps(f.get('evidence', []), indent=2)}</pre>
        </div>
      </details>
    </div>
    ''' for f in r.get('findings', [])[:30])}

    <h2>Coverage Matrix & Attack-Class Declarations</h2>
    <table>
      <thead>
        <tr>
          <th>Threat / Attack Class</th>
          <th>Support Status</th>
          <th>Detection Method</th>
          <th>Required Access</th>
        </tr>
      </thead>
      <tbody>
        {"".join(f'''
        <tr>
          <td><strong>{atk.get('attack_class')}</strong></td>
          <td><span class="badge" style="background:#334155;">{atk.get('support_status')}</span></td>
          <td>{atk.get('detection_method')}</td>
          <td><code>{atk.get('required_access')}</code></td>
        </tr>
        ''' for atk in r.get('coverage', {}).get('attack_classes', []))}
      </tbody>
    </table>

    <h2>Tamper-Evident Audit Chain</h2>
    <p>Chain Status: <strong>{r.get('audit', {}).get('verification_status')}</strong> ({r.get('audit', {}).get('event_count')} chained events)</p>
    <table>
      <thead>
        <tr>
          <th>Seq</th>
          <th>Event Type</th>
          <th>Timestamp</th>
          <th>Event Hash (SHA-256)</th>
        </tr>
      </thead>
      <tbody>
        {"".join(f'''
        <tr>
          <td>{ev.get('sequence_index')}</td>
          <td><code>{ev.get('event_type')}</code></td>
          <td>{ev.get('timestamp')[:19]}</td>
          <td><code>{ev.get('event_hash', '')[:20]}...</code></td>
        </tr>
        ''' for ev in r.get('audit', {}).get('events', [])[:10])}
      </tbody>
    </table>

    <h2>Report Integrity & Non-Repudiation</h2>
    <div class="crypto-verify">
      <div><strong>Report SHA-256 Hash:</strong> {integrity.get('report_hash')}</div>
      <div><strong>Ed25519 Signature:</strong> {integrity.get('signature')}</div>
      <div><strong>Signer Module:</strong> {integrity.get('signer')}</div>
      <div><strong>Algorithm:</strong> {integrity.get('algorithm')}</div>
      <div><strong>Signed At:</strong> {integrity.get('signed_at')}</div>
    </div>
  </div>
</body>
</html>
"""
        return html
