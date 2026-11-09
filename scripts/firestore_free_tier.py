"""Write a free-tier copy of the Firestore index config (D-087).

TTL policies need billing, so on the Spark plan the `ttl: true` flags in
contracts/firestore/firestore.indexes.json are removed (field overrides and
composite indexes are kept). Deploy with:

    .venv/bin/python scripts/firestore_free_tier.py
    .venv/bin/firebase deploy --only firestore --config firebase.free-tier.json --project hireme-engage-dev

Drop this step after the Blaze switch and deploy with the normal firebase.json.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
src = json.loads((ROOT / "contracts/firestore/firestore.indexes.json").read_text())
removed = [f'{o["collectionGroup"]}.{o["fieldPath"]}' for o in src.get("fieldOverrides", []) if o.pop("ttl", False)]
out = ROOT / "build/firestore.indexes.free-tier.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(src, indent=2) + "\n")
print(f"wrote {out.relative_to(ROOT)}; TTL removed on {len(removed)} fields: {', '.join(removed)}")
