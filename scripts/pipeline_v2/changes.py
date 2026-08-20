def _items(catalog: dict) -> dict:
    return {item["canonical_id"]: item for section in ("models", "plans")
            for item in (catalog or {}).get(section, [])}


from typing import Optional


def detect_changes(old: Optional[dict], new: dict) -> list[dict]:
    before, after = _items(old or {}), _items(new)
    changes = []
    for canonical_id in sorted(set(before) | set(after)):
        old_fields = before.get(canonical_id, {}).get("fields", {})
        new_fields = after.get(canonical_id, {}).get("fields", {})
        for field in sorted(set(old_fields) | set(new_fields)):
            if old_fields.get(field) != new_fields.get(field):
                changes.append({"canonical_id": canonical_id, "field": field,
                                "old": old_fields.get(field), "new": new_fields.get(field)})
    return changes
