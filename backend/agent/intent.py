from __future__ import annotations

import re
from typing import Any


VAGUE_CLARIFY_RESPONSE = (
    "I'm here to help you schedule an appointment. "
    "Please tell me the specialty (for example dermatology, cardiology, or general medicine) "
    "and your preferred day or time of day."
)

AWAITING_SELECTION_CLARIFY = (
    "Which of the available times would you prefer? "
    "You can reply with a time like 2:00 PM or 3:30 PM."
)

OFF_TOPIC_RESPONSE = (
    "I can only help with finding, booking, changing, or canceling clinic appointments "
    "(general medicine, dermatology, or cardiology). "
    "Tell me the specialty and preferred day or time, and I can help from there."
)

STRONG_SCHEDULING_KEYWORDS = re.compile(
    r"\b("
    r"appointments?|schedul(e|ing)|book(ing)?|cancel(l?ing|lation)?|"
    r"reschedul(e|ing)|doctor|physician|special(ty|ist)|clinic|"
    r"dermatolog(y|ist)|cardiolog(y|ist)|general\s+medicine|derm|cardio|"
    r"slot|available|availability|"
    r"confirm"
    r")\b",
    re.IGNORECASE,
)

FOLLOWUP_KEYWORDS = re.compile(
    r"\b("
    r"morning|afternoon|evening|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"today|tomorrow|next\s+week|"
    r"am|pm|yes|works|please"
    r")\b",
    re.IGNORECASE,
)

OFF_TOPIC_KEYWORDS = re.compile(
    r"\b("
    r"weather|forecast|temperature|joke|funny|recipe|cook|"
    r"code|coding|python|javascript|program(ming)?|"
    r"stock\s+market|crypto|bitcoin|movie|music|lyrics|"
    r"homework|essay|poem|translate|who\s+won|sports|"
    r"capital\s+of|tell\s+me\s+a\s+story"
    r")\b",
    re.IGNORECASE,
)

DATE_OR_TIME = re.compile(
    r"(\b20\d{2}-\d{2}-\d{2}\b|\b\d{1,2}:\d{2}\b|\b\d{1,2}\s*(am|pm)\b)",
    re.IGNORECASE,
)

# Letters from common scripts (Latin, etc.)
LETTER_RE = re.compile(r"[A-Za-z]")


def _letter_count(text: str) -> int:
    return len(LETTER_RE.findall(text or ""))


def is_vague_message(text: str) -> bool:
    """Empty, whitespace-only, emoji-only, symbols-only, or almost no letters."""
    if text is None:
        return True
    stripped = text.strip()
    if not stripped:
        return True

    letters = _letter_count(stripped)
    if letters >= 3:
        return False

    # Remove letters, digits, and common punctuation; if anything remains (emoji/symbols)
    # or the whole message is punctuation/noise, treat as vague.
    without_alnum = re.sub(r"[A-Za-z0-9\s.,!?'\"\-]", "", stripped)
    if without_alnum and letters < 3:
        return True

    # Pure punctuation / short noise: "???", "...", "ok" alone is NOT vague (2 letters)
    # but "?" or "!!" is vague
    if letters == 0:
        return True

    # 1–2 letters only (e.g. "hi", "ok") — allow short affirmations only when not emoji soup
    if letters <= 2 and not DATE_OR_TIME.search(stripped):
        if STRONG_SCHEDULING_KEYWORDS.search(stripped) or FOLLOWUP_KEYWORDS.search(stripped):
            return False
        return True

    return False


def has_scheduling_signal(text: str, *, allow_followup: bool = True) -> bool:
    if not text:
        return False
    if STRONG_SCHEDULING_KEYWORDS.search(text):
        return True
    if allow_followup and FOLLOWUP_KEYWORDS.search(text):
        return True
    if DATE_OR_TIME.search(text):
        return True
    from agent.state import normalize_specialty

    return normalize_specialty(text) is not None


def is_off_topic(text: str, state: dict[str, Any] | None = None) -> bool:
    """
    Off-topic when the message looks unrelated to scheduling and we are not
    in an active follow-up turn that can accept short answers.
    """
    state = state or {}
    status = state.get("status") or ""
    text = text or ""

    # Explicit off-topic intents win unless there is a strong scheduling ask
    if OFF_TOPIC_KEYWORDS.search(text) and not STRONG_SCHEDULING_KEYWORDS.search(text):
        from agent.state import normalize_specialty

        if normalize_specialty(text) is None:
            return True

    # Active booking flow: short or related follow-ups are not off-topic
    if status in ("awaiting_selection", "collecting_information", "booking_failed", "no_slots"):
        if has_scheduling_signal(text) or is_vague_message(text):
            return False
        return False

    if has_scheduling_signal(text, allow_followup=False) or DATE_OR_TIME.search(text):
        return False

    from agent.state import normalize_specialty

    if normalize_specialty(text):
        return False

    # No strong scheduling signal and no active flow → off topic if it has real words
    if _letter_count(text) >= 8:
        return True

    return False


def intent_check(message: str, state: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """
    Deterministic vague / off-topic gate. Returns a response dict if blocked.
    Call after emergency/diagnosis safety checks.
    """
    state = state or {}
    status = state.get("status") or ""

    if is_vague_message(message):
        if status == "awaiting_selection" and (state.get("last_search_slots") or []):
            return {
                "blocked": True,
                "reason": "vague_awaiting_selection",
                "message": AWAITING_SELECTION_CLARIFY,
            }
        return {
            "blocked": True,
            "reason": "vague_input",
            "message": VAGUE_CLARIFY_RESPONSE,
        }

    if is_off_topic(message, state):
        return {
            "blocked": True,
            "reason": "off_topic",
            "message": OFF_TOPIC_RESPONSE,
        }

    return None
