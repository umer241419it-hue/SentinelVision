import json
import urllib.request
import urllib.error

BRIDGE_URL = "http://localhost:3000/findings"

candidates = [
    "finding-stage5-replay-guard-base",
    "finding-stage5-replay-guard-diff",
    "finding-stage5-replay-baseline",
    "finding-cli-test-replay",
    "finding-stage5-guard-v14-baseline",
    "finding-stage5-guard-v14-replay",
    "finding-stage5-guard-v14-clean",
    "finding-stage5-replay-guard-attack",
    "finding-stage5-replay-attack-replayed",
    "finding-stage5-replay-different"
]

print("=" * 80)
print("PART D: LIVE GET VERIFICATION OF TEST ARTIFACT CANDIDATES")
print("=" * 80)

results = {}
for asset_id in candidates:
    url = f"{BRIDGE_URL}/{asset_id}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results[asset_id] = {"status": resp.status, "committed": True, "data": data}
            print(f"\n[FOUND] {asset_id} (HTTP {resp.status}):")
            print(json.dumps(data, indent=2))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            body_json = json.loads(body)
        except Exception:
            body_json = body
        results[asset_id] = {"status": e.code, "committed": False, "error": body_json}
        print(f"\n[NOT FOUND] {asset_id} (HTTP {e.code}):")
        print(json.dumps(body_json, indent=2) if isinstance(body_json, dict) else body_json)

print("\n" + "=" * 80)
print("SUMMARY OF COMMITTED TEST ARTIFACTS IN WORLD STATE:")
print("=" * 80)
for asset_id, info in results.items():
    print(f"- {asset_id}: {'COMMITTED' if info['committed'] else 'NOT_COMMITTED'} (HTTP {info['status']})")