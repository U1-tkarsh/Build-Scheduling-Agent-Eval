from __future__ import annotations

from copy import deepcopy
from typing import Any


DEFAULT_STATE: dict[str, Any] = {
    "patient_name": None,
    "specialty": None,
    "preferred_date": None,
    "preferred_time": None,
    "selected_slot_id": None,
    "appointment_id": None,
    "status": "collecting_information",
    "last_search_slots": [],
    "simulate_booking_failure": False,
}


def new_state(**overrides: Any) -> dict[str, Any]:
    state = deepcopy(DEFAULT_STATE)
    state.update(overrides)
    return state


def merge_state(state: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(state) if state else new_state()
    for key, value in updates.items():
        if value is not None:
            merged[key] = value
    return merged


SPECIALTY_ALIASES = {
    "dermatologist": "dermatology",
    "derm": "dermatology",
    "skin": "dermatology",
    "cardiologist": "cardiology",
    "heart": "cardiology",
    "cardio": "cardiology",
    "general": "general medicine",
    "gp": "general medicine",
    "primary care": "general medicine",
    "general medicine": "general medicine",
    "dermatology": "dermatology",
    "cardiology": "cardiology",
}


def normalize_specialty(text: str | None) -> str | None:
    if not text:
        return None
    lower = text.lower().strip()
    for alias, canonical in SPECIALTY_ALIASES.items():
        if alias in lower:
            return canonical
    return None
