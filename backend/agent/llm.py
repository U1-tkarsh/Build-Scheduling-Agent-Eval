from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from typing import Any

import httpx
from django.conf import settings

from agent.state import normalize_specialty


class LLMClient:
    """OpenAI-compatible chat completion client."""

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> dict[str, Any]:
        raise NotImplementedError


class OpenAILLMClient(LLMClient):
    """OpenAI-compatible client (works with Gemini's OpenAI-compat endpoint)."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        self.api_key = (api_key or settings.LLM_API_KEY or "").strip()
        self.model = model or settings.LLM_MODEL
        self.base_url = (base_url or settings.LLM_BASE_URL).rstrip("/")

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("LLM_API_KEY is not set")

        # Normalize roles for OpenAI-compat providers (Gemini accepts tool/assistant/user/system)
        normalized = self._normalize_messages(messages)

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": normalized,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # Gemini also accepts x-goog-api-key; helps some key types / gateways
        if "generativelanguage.googleapis.com" in self.base_url:
            headers["x-goog-api-key"] = self.api_key

        try:
            with httpx.Client(timeout=60.0) as client:
                last_error = None
                for attempt in range(2):
                    response = client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                    if response.status_code == 503 and attempt == 0:
                        last_error = response.text[:300]
                        continue
                    if response.status_code >= 400:
                        detail = response.text[:500]
                        raise RuntimeError(
                            f"LLM HTTP {response.status_code} from {self.base_url}: {detail}"
                        )
                    data = response.json()
                    break
                else:
                    raise RuntimeError(
                        f"LLM HTTP 503 from {self.base_url}: {last_error or 'unavailable'}"
                    )
        except httpx.HTTPError as exc:
            raise RuntimeError(f"LLM request failed: {exc}") from exc

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"LLM returned no choices: {data}")

        message = choices[0].get("message") or {}
        tool_calls = []
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            args = function.get("arguments", "{}")
            if isinstance(args, str):
                try:
                    args = json.loads(args or "{}")
                except json.JSONDecodeError:
                    args = {}
            elif not isinstance(args, dict):
                args = {}
            name = function.get("name") or ""
            if not name:
                continue
            entry: dict[str, Any] = {
                "id": call.get("id") or f"call_{name}",
                "name": name,
                "arguments": args,
            }
            # Gemini thinking models require this signature on the next request
            if call.get("extra_content"):
                entry["extra_content"] = call["extra_content"]
            tool_calls.append(entry)

        content = message.get("content")
        if content is None:
            content = ""
        elif isinstance(content, list):
            # Some providers return multimodal content parts
            parts = []
            for part in content:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict) and part.get("text"):
                    parts.append(str(part["text"]))
            content = "".join(parts)

        return {
            "content": content,
            "tool_calls": tool_calls,
        }

    def _normalize_messages(self, messages: list[dict]) -> list[dict]:
        normalized: list[dict] = []
        for msg in messages:
            role = msg.get("role")
            entry: dict[str, Any] = {"role": role, "content": msg.get("content") or ""}
            if role == "assistant" and msg.get("tool_calls"):
                openai_calls = []
                for idx, tc in enumerate(msg["tool_calls"]):
                    call_entry: dict[str, Any] = {
                        "id": tc.get("id") or f"call_{tc.get('name')}",
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc.get("arguments") or {}),
                        },
                    }
                    # Pass Gemini thought_signature back exactly as received
                    extra = tc.get("extra_content")
                    if extra:
                        call_entry["extra_content"] = extra
                    elif (
                        idx == 0
                        and "generativelanguage.googleapis.com" in self.base_url
                    ):
                        # Last-resort bypass for histories that lost the signature
                        call_entry["extra_content"] = {
                            "google": {
                                "thought_signature": "skip_thought_signature_validator"
                            }
                        }
                    openai_calls.append(call_entry)
                entry["tool_calls"] = openai_calls
                if entry["content"] is None:
                    entry["content"] = ""
            if role == "tool":
                entry["name"] = msg.get("name")
                if msg.get("tool_call_id"):
                    entry["tool_call_id"] = msg["tool_call_id"]
            normalized.append(entry)
        return normalized


class FakeLLMClient(LLMClient):
    """
    Deterministic LLM stand-in for demos and reproducible evals.

    Intentionally mirrors a known V1 weakness: when the active prompt lacks an
    explicit booking-verification rule, a failed book_appointment may still be
    described as confirmed. With the rule present (V2+), failure is reported honestly.
    """

    def __init__(self, prompt_has_booking_verification: bool = False, reference_date: date | None = None):
        self.prompt_has_booking_verification = prompt_has_booking_verification
        self.reference_date = reference_date or date(2026, 10, 5)
        self._pending_tool_result: dict[str, Any] | None = None
        self._last_user_message = ""
        self._state_snapshot: dict[str, Any] = {}

    def set_context(self, *, state: dict[str, Any], prompt_has_booking_verification: bool) -> None:
        self._state_snapshot = state or {}
        self.prompt_has_booking_verification = prompt_has_booking_verification

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> dict[str, Any]:
        # If last message is a tool result, produce the final patient-facing reply.
        last = messages[-1] if messages else {}
        if last.get("role") == "tool":
            return self._reply_after_tool(last)

        user_messages = [m for m in messages if m.get("role") == "user"]
        self._last_user_message = user_messages[-1]["content"] if user_messages else ""
        return self._decide_next_action()

    def _decide_next_action(self) -> dict[str, Any]:
        text = self._last_user_message.lower()
        state = self._state_snapshot

        # Preference change: "actually" / "wednesday" etc. clears prior date intent
        if any(w in text for w in ("actually", "instead", "change", "make it")):
            new_specialty = normalize_specialty(text) or state.get("specialty")
            new_date = self._extract_date(text) or state.get("preferred_date")
            new_pref = self._extract_time_pref(text) or state.get("preferred_time")
            if new_specialty and new_date:
                return self._tool(
                    "search_available_slots",
                    {
                        "specialty": new_specialty,
                        "date": new_date,
                        "time_preference": new_pref,
                    },
                )

        specialty = normalize_specialty(text) or state.get("specialty")
        preferred_date = self._extract_date(text) or state.get("preferred_date")
        time_pref = self._extract_time_pref(text) or state.get("preferred_time")

        # Slot selection like "3:30" / "2 PM" / "the second one"
        selected = self._extract_slot_selection(text, state.get("last_search_slots") or [])
        if selected and state.get("status") in ("awaiting_selection", "collecting_information"):
            patient = state.get("patient_name") or "Patient"
            return self._tool(
                "book_appointment",
                {"patient_name": patient, "slot_id": selected},
            )

        # Explicit book request after search
        if "book" in text and state.get("selected_slot_id"):
            return self._tool(
                "book_appointment",
                {
                    "patient_name": state.get("patient_name") or "Patient",
                    "slot_id": state["selected_slot_id"],
                },
            )

        if not specialty:
            return {
                "content": "Happy to help. Which type of doctor or specialty do you need?",
                "tool_calls": [],
            }

        if not preferred_date and not time_pref:
            return {
                "content": (
                    f"I can help you book a {specialty} appointment. "
                    "What date and time of day do you prefer (morning or afternoon)?"
                ),
                "tool_calls": [],
            }

        if not preferred_date:
            return {
                "content": f"What date would you like for your {specialty} appointment?",
                "tool_calls": [],
            }

        return self._tool(
            "search_available_slots",
            {
                "specialty": specialty,
                "date": preferred_date,
                "time_preference": time_pref,
            },
        )

    def _reply_after_tool(self, tool_message: dict) -> dict[str, Any]:
        name = tool_message.get("name", "")
        try:
            result = json.loads(tool_message.get("content") or "{}")
        except json.JSONDecodeError:
            result = {}

        if name == "search_available_slots":
            slots = result.get("slots") or []
            if not slots:
                return {
                    "content": (
                        "I could not find any available slots for that request. "
                        "Would you like to try a different date or time of day?"
                    ),
                    "tool_calls": [],
                }
            lines = []
            for slot in slots:
                start = slot["start_time"]
                try:
                    dt = datetime.fromisoformat(start)
                    label = dt.strftime("%-I:%M %p") if hasattr(dt, "strftime") else start
                    # %-I is not portable on Windows; use fallback
                    label = dt.strftime("%I:%M %p").lstrip("0")
                except ValueError:
                    label = start
                lines.append(f"- {label} with {slot['doctor']} (slot {slot['slot_id']})")
            return {
                "content": (
                    "I found the following available times:\n"
                    + "\n".join(lines)
                    + "\n\nWhich one would you prefer?"
                ),
                "tool_calls": [],
            }

        if name == "book_appointment":
            if result.get("success") and result.get("appointment_id"):
                return {
                    "content": (
                        f"Your appointment is confirmed. "
                        f"Confirmation ID: {result['appointment_id']}."
                    ),
                    "tool_calls": [],
                }
            # V1 weakness: may falsely confirm when verification rule is missing
            if not self.prompt_has_booking_verification:
                return {
                    "content": "Your appointment is confirmed for the selected time.",
                    "tool_calls": [],
                }
            return {
                "content": (
                    "I was not able to complete the booking. "
                    f"{result.get('error', 'Please try another slot.')}"
                ),
                "tool_calls": [],
            }

        if name == "cancel_appointment":
            if result.get("success"):
                return {"content": "Your appointment has been cancelled.", "tool_calls": []}
            return {
                "content": f"I could not cancel that appointment. {result.get('error', '')}",
                "tool_calls": [],
            }

        if name == "get_appointment":
            if result.get("success"):
                appt = result["appointment"]
                return {
                    "content": (
                        f"Appointment {appt['appointment_id']} is {appt['status']} "
                        f"with {appt['doctor']} at {appt['start_time']}."
                    ),
                    "tool_calls": [],
                }
            return {"content": result.get("error", "Appointment not found."), "tool_calls": []}

        return {"content": "How else can I help with your appointment?", "tool_calls": []}

    def _tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "content": "",
            "tool_calls": [{"id": f"call_{name}", "name": name, "arguments": arguments}],
        }

    def _extract_time_pref(self, text: str) -> str | None:
        if "morning" in text:
            return "morning"
        if "afternoon" in text:
            return "afternoon"
        if "evening" in text:
            return "evening"
        return None

    def _extract_date(self, text: str) -> str | None:
        # Explicit ISO date
        match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
        if match:
            return match.group(1)

        ref = self.reference_date
        if "today" in text:
            return ref.isoformat()
        if "tomorrow" in text:
            return (ref + timedelta(days=1)).isoformat()

        weekdays = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }
        for name, weekday in weekdays.items():
            if name in text:
                days_ahead = (weekday - ref.weekday()) % 7
                if days_ahead == 0:
                    days_ahead = 7 if "next" in text else 0
                # "next Tuesday" from Monday Oct 5 -> Oct 6 (1 day) if not requiring full week
                if "next" in text and days_ahead == 0:
                    days_ahead = 7
                elif "next" in text and days_ahead > 0:
                    # keep soonest upcoming day labeled as next
                    pass
                return (ref + timedelta(days=days_ahead if days_ahead else 7)).isoformat()

        return None

    def _extract_slot_selection(self, text: str, slots: list[dict]) -> int | None:
        if not slots:
            return None

        # Match "3:30" / "15:30" / "2:00 PM"
        time_match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", text, re.I)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2) or 0)
            ampm = (time_match.group(3) or "").lower()
            candidates = []
            if ampm == "pm" and hour < 12:
                candidates = [hour + 12]
            elif ampm == "am" and hour == 12:
                candidates = [0]
            elif ampm == "am":
                candidates = [hour]
            elif ampm == "pm":
                candidates = [hour if hour >= 12 else hour + 12]
            else:
                # No am/pm: match both 12h and 24h interpretations
                candidates = [hour]
                if 1 <= hour <= 11:
                    candidates.append(hour + 12)
            for slot in slots:
                try:
                    dt = datetime.fromisoformat(slot["start_time"])
                except ValueError:
                    continue
                if dt.hour in candidates and dt.minute == minute:
                    return slot["slot_id"]

        # "first one" / "second"
        if "first" in text:
            return slots[0]["slot_id"]
        if "second" in text and len(slots) > 1:
            return slots[1]["slot_id"]
        if "third" in text and len(slots) > 2:
            return slots[2]["slot_id"]

        # Exact slot id
        id_match = re.search(r"\bslot\s+(\d+)\b", text)
        if id_match:
            return int(id_match.group(1))

        # If only one option and patient says yes/works/book
        if len(slots) == 1 and any(w in text for w in ("yes", "works", "book", "that one", "confirm")):
            return slots[0]["slot_id"]

        return None


def get_llm_client(*, prompt_has_booking_verification: bool = False) -> LLMClient:
    if settings.USE_FAKE_LLM or not settings.LLM_API_KEY:
        return FakeLLMClient(prompt_has_booking_verification=prompt_has_booking_verification)
    return OpenAILLMClient()
