from __future__ import annotations

from difflib import SequenceMatcher

try:
    from rapidfuzz import fuzz, process
except ImportError:  # keeps the app runnable before optional dependencies are installed
    fuzz = process = None


HONORIFICS = {"bhai", "ji", "didi", "uncle", "aunty", "bhaiya", "जी", "भाई"}
NAME_ALIASES = {
    "रमेश": "ramesh",
    "सुनीता": "sunita",
    "इकबाल": "iqbal",
    "इक़बाल": "iqbal",
    "पूजा": "pooja",
    "मोहन": "mohan",
    "कविता": "kavita",
    "दीपक": "deepak",
    "शबनम": "shabnam",
}


def _normalize(value: str) -> str:
    parts = [part for part in value.casefold().strip().split() if part not in HONORIFICS]
    return " ".join(NAME_ALIASES.get(part, part) for part in parts)


def match_customer(spoken_name: str, existing_names: list[str], threshold: float = 70) -> tuple[str, float]:
    if not existing_names:
        return spoken_name.strip().title(), 100.0
    normalized = _normalize(spoken_name)
    lookup = {_normalize(name): name for name in existing_names}
    if normalized in lookup:
        return lookup[normalized], 100.0
    if process is not None:
        result = process.extractOne(normalized, lookup.keys(), scorer=fuzz.WRatio)
        if result and result[1] >= threshold:
            return lookup[result[0]], float(result[1])
        return spoken_name.strip().title(), float(result[1] if result else 0)
    best = max(lookup, key=lambda candidate: SequenceMatcher(None, normalized, candidate).ratio())
    score = SequenceMatcher(None, normalized, best).ratio() * 100
    return (lookup[best] if score >= threshold else spoken_name.strip().title()), score
