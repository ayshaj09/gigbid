"""Regenerate the tool table in docs/TOOLS.md from the committed schema snapshots."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
rows = []
for server in ("portfolio", "marketplace", "workspace"):
    for t in json.loads((ROOT / "tests/contract/snapshots" / f"{server}.json").read_text(encoding="utf-8")):
        a = t["annotations"] or {}
        rw = "read" if a.get("readOnlyHint") else "write"
        ann = ", ".join(k.replace("Hint", "") for k, v in a.items() if v is True and k.endswith("Hint"))
        auth = {"portfolio": "stdio local / bearer over HTTP", "marketplace": "bearer token -> user (HTTP); stdio local",
                "workspace": "stdio local / bearer over HTTP"}[server]
        extra = " idempotency_key, dry_run" if "idempotency_key" in t["input"].get("properties", {}) else ""
        rows.append(f"| `{t['name']}` | {server} | {rw} | {ann} | {auth}{';' + extra if extra else ''} |")
print("\n".join(["| Tool | Server | Read/write | Annotations | Auth / safety |", "|---|---|---|---|---|"] + rows))
