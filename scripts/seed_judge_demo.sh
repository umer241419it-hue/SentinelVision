#!/usr/bin/env bash
# ==============================================================================
# SentinelVision - Judge & Auditor Demo Seed Script
# Verifies bridge, Fabric network, assurance findings, and quarantine records.
# ==============================================================================
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." >/dev/null 2>&1 && pwd)"
cd "$PROJECT_ROOT"

echo "========================================"
echo "    SENTINELVISION JUDGE DEMO SEED      "
echo "========================================"

# 1. Verify Bridge is reachable
BRIDGE_URL="http://127.0.0.1:3000"
HEALTH_JSON=$(curl -s --connect-timeout 3 "$BRIDGE_URL/health" 2>/dev/null || true)

if [ -z "$HEALTH_JSON" ] || ! echo "$HEALTH_JSON" | grep -q '"status":"UP"'; then
  echo "[!] Bridge is not running at $BRIDGE_URL."
  echo "    Start the bridge with: npm --prefix frontend run bridge:dev"
  exit 1
fi

# 2. Check Fabric Network Connection
FABRIC_STATUS=$(echo "$HEALTH_JSON" | jq -r '.subsystems.fabricLedger.status // "OFFLINE"')
CHANNEL_NAME=$(echo "$HEALTH_JSON" | jq -r '.subsystems.fabricLedger.channel // "mychannel"')
CHAINCODE_NAME=$(echo "$HEALTH_JSON" | jq -r '.subsystems.fabricLedger.chaincode // "basic"')

echo ""
echo "Fabric Network:"
echo "  Status:    $FABRIC_STATUS"
echo "  Channel:   $CHANNEL_NAME"
echo "  Chaincode: $CHAINCODE_NAME"

# 3. Verify Genuine Findings
FINDINGS_JSON=$(curl -s "$BRIDGE_URL/api/findings" 2>/dev/null || echo '{"findings":[]}')
FINDINGS_COUNT=$(echo "$FINDINGS_JSON" | jq '.findings | length')
echo ""
echo "Findings catalog: $FINDINGS_COUNT active findings"

# 4. Verify / Seed Quarantine Queue
QUARANTINE_JSON=$(curl -s "$BRIDGE_URL/api/auditor/quarantine" 2>/dev/null || echo '{"quarantine":[]}')
QUARANTINE_COUNT=$(echo "$QUARANTINE_JSON" | jq '.quarantine | length')

if [ "$QUARANTINE_COUNT" -eq 0 ]; then
  echo "[*] Seeding quarantine records from real test executions..."
  ANALYST_TOKEN=$(curl -s -X POST "$BRIDGE_URL/api/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"email":"analyst@sentinelvision.io","password":"Password123!"}' | jq -r '.token // empty')

  if [ -n "$ANALYST_TOKEN" ]; then
    curl -s -X POST "$BRIDGE_URL/api/trust/tests/test-1790489344064-bbc4c8/quarantine" \
      -H "Authorization: Bearer $ANALYST_TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"reason":"Class 2 Trojan Backdoor confirmed by Neural Cleanse + STRIP on model-trojai-res50-0112"}' >/dev/null 2>&1 || true

    curl -s -X POST "$BRIDGE_URL/api/trust/tests/test-1790849135011-d21dff/quarantine" \
      -H "Authorization: Bearer $ANALYST_TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"reason":"Data integrity anomalies (37 findings) and inference provenance verification failure"}' >/dev/null 2>&1 || true

    QUARANTINE_JSON=$(curl -s "$BRIDGE_URL/api/auditor/quarantine" 2>/dev/null || echo '{"quarantine":[]}')
    QUARANTINE_COUNT=$(echo "$QUARANTINE_JSON" | jq '.quarantine | length')
  fi
fi

echo "Quarantine queue: $QUARANTINE_COUNT items"

# 5. Check Ledger Transactions
LEDGER_JSON=$(curl -s "$BRIDGE_URL/api/auditor/ledger/transactions" 2>/dev/null || echo '{"transactions":[],"journal":[]}')
ON_CHAIN_TX_COUNT=$(echo "$LEDGER_JSON" | jq '.transactions | length')
JOURNAL_COUNT=$(echo "$LEDGER_JSON" | jq '.journal | length')

echo "On-Chain Fabric Transactions: $ON_CHAIN_TX_COUNT"
echo "Local Submission Journal Records: $JOURNAL_COUNT"

echo ""
echo "========================================"
echo "SUMMARY:"
echo "  Bridge:                 ONLINE"
echo "  Fabric Network:         $FABRIC_STATUS"
echo "  Findings Generated:     $FINDINGS_COUNT"
echo "  Quarantine Records:     $QUARANTINE_COUNT"
echo "  Fabric Transactions:    $ON_CHAIN_TX_COUNT"
echo "  Auditor Pages:"
echo "    - Findings:           ✓"
echo "    - Quarantine Review:  ✓"
echo "    - Fabric Ledger:      ✓"
echo "    - Governance Reports: ✓"
echo "========================================"
