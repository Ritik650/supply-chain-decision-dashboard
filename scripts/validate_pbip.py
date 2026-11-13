"""Validate the generated Power BI Project before opening it in Power BI Desktop.

1. Every report JSON file is validated against the Microsoft JSON schema named in its "$schema"
   (schemas are downloaded once and cached in data/interim/pbir_schemas/).
2. Every field a visual references (Entity.Property) must exist in the semantic model.
3. The TMDL folder is parsed by Microsoft's own TmdlSerializer from the local Power BI Desktop install.

    python scripts/validate_pbip.py
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from jsonschema import Draft7Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
PBI = ROOT / "dashboard" / "powerbi"
REPORT = PBI / "supply_chain_dashboard.Report"
MODEL = PBI / "supply_chain_dashboard.SemanticModel" / "definition"
CACHE = ROOT / "data" / "interim" / "pbir_schemas"
TABULAR_DLL = Path(r"C:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.PowerBI.Tabular.dll")


def fetch(url: str) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".json")
    if not f.exists():
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        f.write_bytes(r.content)
    return json.loads(f.read_text(encoding="utf-8-sig"))


def retrieve(uri: str) -> Resource:
    return Resource.from_contents(fetch(uri.split("#")[0]))


def validate_json() -> list[str]:
    problems = []
    registry = Registry(retrieve=retrieve)
    # .pbi/ holds Desktop's local editor settings, which are not part of the report definition.
    files = [p for p in REPORT.rglob("*.json") if "StaticResources" not in p.parts and ".pbi" not in p.parts]
    # Power BI Desktop omits "$schema" from these three files when it saves; that is allowed.
    optional = {REPORT / "definition.pbir", PBI / "supply_chain_dashboard.pbip", MODEL.parent / "definition.pbism"}
    files += sorted(optional)
    for f in files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        url = doc.get("$schema")
        if not url:
            if f not in optional:
                problems.append(f"{f.relative_to(PBI)}: no $schema")
            continue
        schema = fetch(url)
        schema.setdefault("$id", url)
        v = Draft7Validator(schema, registry=registry)
        for err in sorted(v.iter_errors(doc), key=lambda e: list(e.absolute_path)):
            where = "/".join(str(x) for x in err.absolute_path)
            problems.append(f"{f.relative_to(PBI)}: {where}: {err.message[:200]}")
    print(f"  JSON schema: {len(files)} files checked, {len(problems)} problem(s)")
    return problems


def model_fields() -> set[tuple[str, str]]:
    fields = set()
    for f in (MODEL / "tables").glob("*.tmdl"):
        table = None
        for line in f.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^table (.+)$", line)
            if m:
                table = m.group(1).strip().strip("'").replace("''", "'")
            m = re.match(r"^\t(column|measure) ('(?:[^']|'')+'|[^ =]+)", line)
            if m and table:
                fields.add((table, m.group(2).strip("'").replace("''", "'")))
    return fields


def validate_refs() -> list[str]:
    known = model_fields()
    problems = []

    def walk(o, f):
        if isinstance(o, dict):
            for kind in ("Column", "Measure"):
                if kind in o and isinstance(o[kind], dict) and "Property" in o[kind]:
                    src = o[kind].get("Expression", {}).get("SourceRef", {})
                    ent = src.get("Entity")
                    if ent and (ent, o[kind]["Property"]) not in known:
                        problems.append(f"{f.relative_to(PBI)}: unknown field {ent}[{o[kind]['Property']}]")
            for v in o.values():
                walk(v, f)
        elif isinstance(o, list):
            for v in o:
                walk(v, f)

    for f in REPORT.rglob("*.json"):
        if "StaticResources" not in f.parts:
            walk(json.loads(f.read_text(encoding="utf-8")), f)
    print(f"  Field references: {len(known)} model fields, {len(problems)} unknown reference(s)")
    return problems


def validate_tmdl() -> list[str]:
    if not TABULAR_DLL.exists():
        print("  TMDL: Power BI Desktop not found, skipped")
        return []
    ps = (f"Add-Type -Path '{TABULAR_DLL}'; "
          f"try {{ $db = [Microsoft.AnalysisServices.Tabular.TmdlSerializer]::DeserializeDatabaseFromFolder('{MODEL}'); "
          "'OK ' + $db.Model.Tables.Count + ' tables, ' + ($db.Model.Tables | % { $_.Measures.Count } | Measure-Object -Sum).Sum + ' measures' } "
          "catch { 'FAILED ' + $_.Exception.Message }")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout.strip()
    print(f"  TMDL: {out}")
    return [] if out.startswith("OK") else [out]


def main() -> int:
    problems = validate_json() + validate_refs() + validate_tmdl()
    for p in problems[:60]:
        print("   -", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
