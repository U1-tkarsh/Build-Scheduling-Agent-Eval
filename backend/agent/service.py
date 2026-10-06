from __future__ import annotations

import json
import re
import uuid
from copy import deepcopy
from datetime import date, datetime, timedelta
from typing import Any

from agent.llm import FakeLLMClient, get_llm_client
from agent.intent import intent_check
from agent.prompt_manager import PromptManager
from agent.safety import safety_check
from agent.state import merge_state, new_state, normalize_specialty
from agent.tools import TOOL_DEFINITIONS, execute_tool
from scheduling.models import Conversation


CONFIRMATION_CLAIM_RE = re.compile(
    r"\b(confirmed|booked|scheduled|confirmation id)\b",
    re.IGNORECASE,
)


class SchedulingAgent:
    """Orchestrates safety -> prompt -> LLM -> tools -> structured state."""

    def __init__(
        self,
        *,
        prompt_version: str | None = None,
        llm=None,
        reference_date: date | None = None,
        force_simulate_booking_failure: bool | None = None,
    ):
        self.prompt_manager = PromptManager()
        if prompt_version:
            self.prompt_version = prompt_version
            self.system_prompt = self.prompt_manager.read_file(prompt_version)
        else:
            self.prompt_version, self.system_prompt = self.prompt_manager.get_active_prompt()

        self.has_booking_verification = self.prompt_manager.has_booking_verification_rule(
            self.system_prompt
        )
        self.llm = llm or get_llm_client(
            prompt_has_booking_verification=self.has_booking_verification
        )
        self.reference_date = reference_date or date(2026, 10, 5)
        self.force_simulate_booking_failure = force_simulate_booking_failure

    def handle_message(
        self,
        conversation_id: str | None,
        user_message: str,
        *,
        eval_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        conversation = self._get_or_create_conversation(conversation_id)
        state = merge_state(conversation.state_json or {}, {})
        messages = list(conversation.messages_json or [])
        tool_logs = list(conversation.tool_logs_json or [])

        overrides = eval_overrides or {}
        if overrides.get("simulate_booking_failure"):
            state["simulate_booking_failure"] = True
        if self.force_simulate_booking_failure is True:
            state["simulate_booking_failure"] = True

        # Deterministic safety gate (before LLM)
        blocked = safety_check(user_message)
        if blocked:
            reply = blocked["message"]
            messages.append({"role": "user", "content": user_message})
            messages.append({"role": "assistant", "content": reply})
            state["status"] = blocked["reason"]
            self._persist(conversation, state, messages, tool_logs)
            return {
                "conversation_id": conversation.id,
                "message": reply,
                "state": state,
                "tool_logs": tool_logs,
                "prompt_version": self.prompt_version,
                "safety": blocked["reason"],
            }

        # Vague / off-topic gate (before LLM) — preserve awaiting_selection for follow-ups
        blocked = intent_check(user_message, state)
        if blocked:
            reply = blocked["message"]
            messages.append({"role": "user", "content": user_message})
            messages.append({"role": "assistant", "content": reply})
            if blocked["reason"] != "vague_awaiting_selection":
                state["status"] = blocked["reason"]
            self._persist(conversation, state, messages, tool_logs)
            return {
                "conversation_id": conversation.id,
                "message": reply,
                "state": state,
                "tool_logs": tool_logs,
                "prompt_version": self.prompt_version,
                "safety": blocked["reason"],
            }

        # Extract structured hints from the user text into state
        state = self._update_state_from_user_text(state, user_message)
        messages.append({"role": "user", "content": user_message})

        if isinstance(self.llm, FakeLLMClient):
            self.llm.set_context(
                state=state,
                prompt_has_booking_verification=self.has_booking_verification,
            )
            self.llm.reference_date = self.reference_date

        llm_messages = self._build_llm_messages(messages, state)
        response = self.llm.complete(llm_messages, tools=TOOL_DEFINITIONS)

        # Tool loop (bounded)
        for _ in range(4):
            tool_calls = response.get("tool_calls") or []
            if not tool_calls:
                break

            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": response.get("content") or "",
                "tool_calls": tool_calls,
            }
            messages.append(assistant_msg)
            llm_messages.append(assistant_msg)

            for call in tool_calls:
                name = call["name"]
                arguments = call.get("arguments") or {}
                simulate_failure = bool(state.get("simulate_booking_failure")) and name == "book_appointment"

                # Idempotent duplicate booking: if already confirmed, return existing
                if (
                    name == "book_appointment"
                    and state.get("appointment_id")
                    and state.get("status") == "confirmed"
                    and not simulate_failure
                ):
                    result = {
                        "success": True,
                        "appointment_id": state["appointment_id"],
                        "status": "confirmed",
                        "idempotent": True,
                    }
                else:
                    result = execute_tool(
                        name,
                        arguments,
                        simulate_booking_failure=simulate_failure,
                    )

                log_entry = {"tool": name, "input": arguments, "output": result}
                tool_logs.append(log_entry)
                state = self._apply_tool_result(state, name, arguments, result)

                tool_msg = {
                    "role": "tool",
                    "name": name,
                    "tool_call_id": call.get("id"),
                    "content": json.dumps(result),
                }
                messages.append(tool_msg)
                llm_messages.append(tool_msg)

            if isinstance(self.llm, FakeLLMClient):
                self.llm.set_context(
                    state=state,
                    prompt_has_booking_verification=self.has_booking_verification,
                )
            response = self.llm.complete(llm_messages, tools=TOOL_DEFINITIONS)

        reply = (response.get("content") or "").strip()
        if not reply:
            reply = "How else can I help with your appointment?"

        # Backend truth override: never allow false confirmation when verification rule present
        # and booking failed. (Also used as a safety net for real LLMs.)
        if self.has_booking_verification:
            last_book = next(
                (t for t in reversed(tool_logs) if t["tool"] == "book_appointment"),
                None,
            )
            if last_book and not last_book["output"].get("success"):
                if CONFIRMATION_CLAIM_RE.search(reply):
                    reply = (
                        "I was not able to complete the booking. "
                        f"{last_book['output'].get('error', 'Please try another slot.')}"
                    )

        messages.append({"role": "assistant", "content": reply})
        self._persist(conversation, state, messages, tool_logs)

        return {
            "conversation_id": conversation.id,
            "message": reply,
            "state": state,
            "tool_logs": tool_logs,
            "prompt_version": self.prompt_version,
            "messages": messages,
        }

    def reset_conversation(self, conversation_id: str | None = None) -> dict[str, Any]:
        new_id = conversation_id or str(uuid.uuid4())
        Conversation.objects.filter(id=new_id).delete()
        conversation = Conversation.objects.create(
            id=new_id,
            state_json=new_state(),
            messages_json=[],
            tool_logs_json=[],
        )
        return {
            "conversation_id": conversation.id,
            "state": conversation.state_json,
            "message": "Conversation reset.",
        }

    def _get_or_create_conversation(self, conversation_id: str | None) -> Conversation:
        cid = conversation_id or str(uuid.uuid4())
        conversation, created = Conversation.objects.get_or_create(
            id=cid,
            defaults={
                "state_json": new_state(),
                "messages_json": [],
                "tool_logs_json": [],
            },
        )
        if created and not conversation.state_json:
            conversation.state_json = new_state()
            conversation.save(update_fields=["state_json"])
        return conversation

    def _persist(
        self,
        conversation: Conversation,
        state: dict,
        messages: list,
        tool_logs: list,
    ) -> None:
        conversation.state_json = state
        conversation.messages_json = messages
        conversation.tool_logs_json = tool_logs
        conversation.save()

    def _build_llm_messages(self, messages: list[dict], state: dict) -> list[dict]:
        system = (
            f"{self.system_prompt}\n\n"
            f"Current structured state (source of truth for IDs):\n"
            f"{json.dumps(state, indent=2)}\n"
            f"Reference date for relative phrases: {self.reference_date.isoformat()}"
        )
        llm_messages: list[dict] = [{"role": "system", "content": system}]
        for msg in messages:
            role = msg.get("role")
            if role == "tool":
                llm_messages.append(
                    {
                        "role": "tool",
                        "name": msg.get("name"),
                        "tool_call_id": msg.get("tool_call_id"),
                        "content": msg.get("content", ""),
                    }
                )
            elif role in ("user", "assistant"):
                entry: dict[str, Any] = {"role": role, "content": msg.get("content") or ""}
                if msg.get("tool_calls"):
                    entry["tool_calls"] = msg["tool_calls"]
                llm_messages.append(entry)
        return llm_messages

    def _update_state_from_user_text(self, state: dict, text: str) -> dict:
        updates: dict[str, Any] = {}
        specialty = normalize_specialty(text)
        if specialty:
            updates["specialty"] = specialty

        lower = text.lower()
        if "morning" in lower:
            updates["preferred_time"] = "morning"
        elif "afternoon" in lower:
            updates["preferred_time"] = "afternoon"
        elif "evening" in lower:
            updates["preferred_time"] = "evening"

        date_str = self._extract_date(lower)
        if date_str:
            # Preference change: discard prior selection
            if any(w in lower for w in ("actually", "instead", "make it", "change")):
                updates["selected_slot_id"] = None
                updates["last_search_slots"] = []
                updates["status"] = "collecting_information"
            updates["preferred_date"] = date_str

        name_match = re.search(r"(?:my name is|i am|i'm)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", text)
        if name_match:
            updates["patient_name"] = name_match.group(1)

        if not state.get("patient_name"):
            updates.setdefault("patient_name", "Patient")

        return merge_state(state, updates)

    def _extract_date(self, text: str) -> str | None:
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
                if "next" in text and days_ahead == 0:
                    days_ahead = 7
                elif days_ahead == 0 and "next" not in text:
                    days_ahead = 0
                elif "next" not in text and days_ahead == 0:
                    days_ahead = 0
                if days_ahead == 0 and name in text and "next" in text:
                    days_ahead = 7
                # From Monday, "next Tuesday" -> +1 day (Tue)
                if days_ahead == 0:
                    target = ref
                else:
                    target = ref + timedelta(days=days_ahead)
                return target.isoformat()
        return None

    def _apply_tool_result(
        self,
        state: dict,
        name: str,
        arguments: dict,
        result: dict,
    ) -> dict:
        updated = deepcopy(state)
        if name == "search_available_slots":
            slots = result.get("slots") or []
            updated["last_search_slots"] = slots
            updated["specialty"] = arguments.get("specialty") or updated.get("specialty")
            updated["preferred_date"] = arguments.get("date") or updated.get("preferred_date")
            updated["preferred_time"] = arguments.get("time_preference") or updated.get(
                "preferred_time"
            )
            updated["selected_slot_id"] = None
            updated["status"] = "awaiting_selection" if slots else "no_slots"
        elif name == "book_appointment":
            if result.get("success") and result.get("appointment_id"):
                updated["appointment_id"] = result["appointment_id"]
                updated["selected_slot_id"] = arguments.get("slot_id")
                updated["patient_name"] = arguments.get("patient_name") or updated.get(
                    "patient_name"
                )
                updated["status"] = "confirmed"
            else:
                updated["status"] = "booking_failed"
        elif name == "cancel_appointment" and result.get("success"):
            updated["status"] = "cancelled"
            updated["appointment_id"] = None
        return updated
