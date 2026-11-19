"""Validation des identités et normalisation des instants du socle."""

from datetime import datetime, timezone
from uuid import UUID

INSTANTS = {"cree_le", "modifie_le", "archive_le", "valide_le", "decide_le",
            "resolu_le", "lu_le", "horodatage"}


def canonical_uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("UUID attendu en texte canonique")
    try:
        canonical = str(UUID(value))
    except ValueError as exc:
        raise ValueError("UUID invalide") from exc
    if value != canonical:
        raise ValueError("UUID non canonique")
    return value


def canonical_instant(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("instant attendu en texte avec fuseau")
    try:
        instant = datetime.fromisoformat(value)
        if instant.utcoffset() is None:
            raise ValueError("instant sans fuseau")
        return instant.astimezone(timezone.utc).isoformat(timespec="microseconds")
    except (ValueError, OverflowError) as exc:
        raise ValueError("instant invalide ou sans fuseau") from exc


def normalize_values(values: dict, nullable: set[str], integer_columns: set[str]) -> None:
    for key, value in values.items():
        if key in integer_columns:
            if type(value) is not int and not (value is None and key in nullable):
                raise ValueError(f"{key} doit être un entier JSON")
            continue
        is_uuid = key not in integer_columns and (
            key in {"id", "cle_stable"} or key.endswith(("_id", "_par"))
        )
        if not is_uuid and key not in INSTANTS:
            continue
        if value is None and key in nullable:
            continue
        values[key] = canonical_uuid(value) if is_uuid else canonical_instant(value)
