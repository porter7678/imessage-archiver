import re
from pathlib import Path
from . import config


def _normalize_phone(raw: str) -> str:
    """Strip formatting; return last 10 digits for US numbers, full digits otherwise."""
    digits = re.sub(r"\D", "", raw)
    return digits[-10:] if len(digits) >= 10 else digits


def _parse_vcf(path: Path) -> dict[str, str]:
    """Return {normalized_key → display_name} from a vCard file."""
    lookup: dict[str, str] = {}

    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    # Unfold continuation lines (lines starting with a space or tab)
    unfolded: list[str] = []
    for line in lines:
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] = unfolded[-1].rstrip("\r\n") + line.lstrip(" \t")
        else:
            unfolded.append(line)

    card: dict[str, list[str]] = {}
    in_card = False

    for raw_line in unfolded:
        line = raw_line.strip()
        if line == "BEGIN:VCARD":
            card = {}
            in_card = True
            continue
        if line == "END:VCARD":
            if not in_card:
                continue
            in_card = False

            # Resolve display name: prefer FN, fall back to N
            name = card.get("FN", "").strip()
            if not name:
                n_parts = card.get("N", "").split(";")
                # N is "Family;Given;Additional;Prefix;Suffix"
                family = n_parts[0].strip() if len(n_parts) > 0 else ""
                given = n_parts[1].strip() if len(n_parts) > 1 else ""
                name = f"{given} {family}".strip() or f"{family}".strip()

            if not name:
                continue

            # Index all phone numbers
            for key, val in card.items():
                if "TEL" in key.upper():
                    norm = _normalize_phone(val)
                    if norm and norm not in lookup:
                        lookup[norm] = name

            # Index email addresses
            for key, val in card.items():
                if "EMAIL" in key.upper():
                    email = val.strip().lower()
                    if email and email not in lookup:
                        lookup[email] = name

            continue

        if not in_card:
            continue

        # Parse "PROPERTY;PARAMS:VALUE" — first ':' separates prop from value
        colon = line.find(":")
        if colon == -1:
            continue
        prop_part = line[:colon].upper()
        value = line[colon + 1:]

        # Grab the base property name (before any ';')
        base_prop = prop_part.split(";")[0]

        # We only care about FN, N, TEL (and item-grouped variants), EMAIL
        if base_prop in ("FN", "N"):
            card[base_prop] = value
        elif "TEL" in prop_part or "EMAIL" in prop_part:
            # Use the full prop line as key to allow multiple entries
            card[prop_part] = value

    return lookup


_cache: dict[str, str] | None = None


def _get_lookup() -> dict[str, str]:
    global _cache
    if _cache is None:
        _cache = _parse_vcf(config.CONTACTS_VCF)
    return _cache


def resolve(handle_id: str) -> str | None:
    """Return display name for a phone number or email, or None if not found."""
    if not handle_id:
        return None
    lookup = _get_lookup()

    # Try as email first (case-insensitive)
    by_email = lookup.get(handle_id.strip().lower())
    if by_email:
        return by_email

    # Try as phone (last-10-digit normalization)
    norm = _normalize_phone(handle_id)
    if norm:
        return lookup.get(norm)
    return None


def contact_count() -> int:
    return len(_get_lookup())
