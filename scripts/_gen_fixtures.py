"""Générateur local des fixtures synthétiques."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts._audit_fixtures import pre_audit  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "journai" / "fixtures"
T0 = "2026-01-05T09:00:00.000000+00:00"
T1 = "2026-02-10T09:00:00.000000+00:00"
T2 = "2026-03-02T10:00:00.000000+00:00"
SPACES = {"a850d82b-814e-540f-bf03-ef86588e90b9": "a",
          "3d1510c4-5e02-54cf-8870-1fef5b8109bc": "b"}


def audit(sets, tables):
    audit_rows(tables)


def audit_rows(tables):
    problems = pre_audit(tables)
    if problems:
        sys.exit("\n".join(problems))


rows = {}


def add(table, *values):
    rows.setdefault(table, []).extend(values)


def meta(who, when=T0):
    return {"cree_par": who, "cree_le": when}


def space(table, row, memberships):
    if table == "utilisateur":
        spaces = memberships.get(row.get("id"), set())
    else:
        space_id = row.get("id") if table == "espace" else row.get("espace_id")
        spaces = {space_id} if space_id in SPACES else set()
    if len(spaces) != 1 or not spaces <= SPACES.keys():
        raise ValueError(f"{table} : appartenance inconnue ou ambiguë : {row}")
    return SPACES[next(iter(spaces))]


def emit(tables, updates=()):
    audit_rows(tables)
    memberships = {}
    for row in tables.get("membre_espace", []):
        memberships.setdefault(row["utilisateur_id"], set()).add(row["espace_id"])
    payloads = {name: {"env": "dev", "tables": [], "updates": []} for name in ("a", "b")}
    owners = {}
    for table, items in tables.items():
        split = {"a": [], "b": []}
        for row in items:
            name = space(table, row, memberships)
            split[name].append(row)
            if "id" in row:
                key = (table, row["id"])
                if key in owners:
                    raise ValueError(f"identifiant dupliqué : {key}")
                owners[key] = name
        for name, kept in split.items():
            if kept:
                payloads[name]["tables"].append({"table": table, "rows": kept})
    for update in updates:
        key = (update["table"], update["id"])
        if key not in owners:
            raise ValueError(f"update sans appartenance : {key}")
        payloads[owners[key]]["updates"].append(update)
    for name, payload in payloads.items():
        (OUT / f"espace-{name}.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"espace-{name}.json {len(payload['tables'])} tables")
