"""Checks in code on what the models found (I11). Only the requirement's own attributes, no website values."""
import re

from calc import number

NONE = re.compile(r"(none|no|n/?a|kein\w*|ohne|nicht|entf\w*|-+)$|(none|no|kein\w*|ohne|nicht)\b", re.I)  # words for "none"


def _text(value) -> str:
    """The attribute as comparable letters and digits; empty when the page says there is none (in any wording that
    starts with a word for "none", e.g. "none required")."""
    raw = str(value or "").strip()
    return "" if not raw or NONE.match(raw) else re.sub(r"[^0-9a-zäöüß]", "", raw.lower())


def material_mismatch(requirement: dict, found: dict) -> list[str]:
    """How the chosen material differs from the requirement, as the kept pages show it (rule 3). An attribute the
    extraction could not read is not compared, so a missing value never blocks a correct pick."""
    differences = []
    for key in ("bore_mm", "stroke_mm", "pressure_bar"):
        want, got = requirement.get(key), found.get(key)
        if want not in (None, "") and got not in (None, "") and number(want) != number(got):
            differences.append(f"{key} is {got}, the requirement needs {want}")
    for key in ("mounting", "certification"):
        want, got = _text(requirement.get(key)), _text(found.get(key))
        if found.get(key) is not None and want != got and not (want and got and (want in got or got in want)):
            differences.append(f"{key} is {found.get(key)!r}, the requirement needs {requirement.get(key)!r}")
    return differences
