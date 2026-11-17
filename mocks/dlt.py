"""TRAI DLT template registry for the mock SMS gateway.

Operators deliver an SMS only if its body matches the registered template, where each variable may be up to
30 characters (DLT `{#var#}`). Templates are registered from the engine's SMS templates
(contracts/examples/templates and templates/, field `dlt`), or through POST /mock/admin/dlt.
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path

import yaml

PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
MAX_VAR = 30


def template_regex(body: str) -> re.Pattern:
    parts, pos = [], 0
    for m in PLACEHOLDER.finditer(body):
        parts.append(re.escape(body[pos:m.start()]))
        parts.append(f"(?P<{m.group(1)}>.{{1,{MAX_VAR}}}?)")
        pos = m.end()
    parts.append(re.escape(body[pos:]))
    return re.compile("^" + "".join(parts) + "$", re.S)


class DltRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self._t: dict[str, dict] = {}

    def register(self, template_id: str, body: str, sender_id: str, category: str) -> None:
        with self._lock:
            self._t[template_id] = {"body": body, "sender_id": sender_id, "category": category,
                                    "regex": template_regex(body)}

    def check(self, req: dict) -> str | None:
        """None if the SMS matches its registered template, else a reason."""
        t = self._t.get(req["dlt"]["template_id"])
        if not t:
            return "template_id not registered"
        if req["sender_id"] != t["sender_id"]:
            return f"sender_id {req['sender_id']} is not registered for this template"
        if req["dlt"]["category"] != t["category"]:
            return f"category {req['dlt']['category']} differs from the registered {t['category']}"
        m = t["regex"].match(req["body"])
        if not m:
            return "body does not match the registered template"
        for k, v in (req.get("template_vars") or {}).items():
            if k in m.groupdict() and m.group(k) != v:
                return f"variable {k} differs from template_vars"
        return None

    def __len__(self) -> int:
        return len(self._t)

    def load_dirs(self, dirs: list[Path]) -> int:
        n = 0
        for d in dirs:
            for p in sorted(d.glob("*")) if d.is_dir() else []:
                if p.suffix not in (".json", ".yaml", ".yml"):
                    continue
                doc = json.loads(p.read_text()) if p.suffix == ".json" else yaml.safe_load(p.read_text())
                if isinstance(doc, dict) and doc.get("channel") == "sms" and doc.get("dlt"):
                    dlt = doc["dlt"]
                    self.register(dlt["template_id"], doc["body"], dlt["sender_id"], dlt["category"])
                    n += 1
        return n
