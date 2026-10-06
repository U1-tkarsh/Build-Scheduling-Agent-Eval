from __future__ import annotations

import re
from typing import Any


EMERGENCY_PATTERNS = [
    r"\bchest\s+pain\b",
    r"\bdifficulty\s+breathing\b",
    r"\bshort(ness)?\s+of\s+breath\b",
    r"\bsevere\s+bleeding\b",
    r"\bunconscious\b",
    r"\bstroke\s+symptoms?\b",
    r"\bsuicidal\s+thoughts?\b",
    r"\bsuicide\b",
    r"\bheart\s+attack\b",
    r"\bcannot\s+breathe\b",
]

EMERGENCY_RESPONSE = (
    "Your symptoms may require urgent medical attention. "
    "Please contact local emergency services or go to the nearest emergency department. "
    "I should not delay urgent care by scheduling a routine appointment."
)

DIAGNOSIS_PATTERNS = [
    r"\bdo\s+i\s+have\b",
    r"\bdoes\s+this\b.*\bmean\b",
    r"\bdiagnos",
    r"\bis\s+this\s+(a\s+)?(heart\s+disease|cancer|stroke|infection)\b",
]

DIAGNOSIS_RESPONSE = (
    "I'm not able to diagnose medical conditions. "
    "Please speak with a qualified clinician about your symptoms. "
    "If you are experiencing severe symptoms such as chest pain or difficulty breathing, "
    "seek emergency care immediately."
)


def detect_emergency(message: str) -> bool:
    text = message.lower()
    return any(re.search(pattern, text) for pattern in EMERGENCY_PATTERNS)


def detect_diagnosis_request(message: str) -> bool:
    text = message.lower()
    return any(re.search(pattern, text) for pattern in DIAGNOSIS_PATTERNS)


def safety_check(message: str) -> dict[str, Any] | None:
    """Deterministic guard before the LLM. Returns a response dict if blocked."""
    # Diagnosis questions first so "does chest pain mean..." is handled as no-diagnosis,
    # while "I have chest pain and want an appointment" still escalates as emergency.
    if detect_diagnosis_request(message):
        return {
            "blocked": True,
            "reason": "no_diagnosis",
            "message": DIAGNOSIS_RESPONSE,
        }
    if detect_emergency(message):
        return {
            "blocked": True,
            "reason": "emergency",
            "message": EMERGENCY_RESPONSE,
        }
    return None
