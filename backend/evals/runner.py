from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.db import transaction

from agent.llm import FakeLLMClient
from agent.prompt_manager import PromptManager
from agent.service import SchedulingAgent
from evals.scenarios import SCENARIOS
from evals.scorers import score_scenario
from scheduling.models import Appointment, AppointmentSlot, Conversation


class EvalRunner:
    def __init__(self, prompt_version: str | None = None):
        self.prompt_version = prompt_version
        # Evals must never call a live LLM (quota / nondeterminism)
        settings.USE_FAKE_LLM = True

    def run_all(self) -> dict[str, Any]:
        results = []
        for scenario in SCENARIOS:
            results.append(self.run_scenario(scenario))
        return self._summarize(results)

    def run_scenario(self, scenario: dict[str, Any]) -> dict[str, Any]:
        conversation_id = f"eval-{scenario['id']}-{uuid.uuid4().hex[:8]}"

        with transaction.atomic():
            # Isolate side effects per scenario via unique conversation;
            # appointments still hit the shared DB — reset scenario-related bookings after.
            pm = PromptManager()
            version = self.prompt_version or pm.get_active_version()
            prompt = pm.read_file(version)
            llm = FakeLLMClient(
                prompt_has_booking_verification=pm.has_booking_verification_rule(prompt)
            )
            agent = SchedulingAgent(prompt_version=version, llm=llm)
            final_response: dict[str, Any] = {}
            overrides = scenario.get("eval_overrides") or {}

            for turn in scenario["conversation"]:
                if turn["role"] != "user":
                    continue
                final_response = agent.handle_message(
                    conversation_id,
                    turn["content"],
                    eval_overrides=overrides,
                )

            state = final_response.get("state") or {}
            tool_logs = final_response.get("tool_logs") or []
            messages = final_response.get("messages") or []
            # Reload messages from DB if needed
            conversation = Conversation.objects.filter(id=conversation_id).first()
            if conversation:
                messages = conversation.messages_json or messages
                tool_logs = conversation.tool_logs_json or tool_logs
                state = conversation.state_json or state

            result = score_scenario(
                scenario,
                final_state=state,
                final_message=final_response.get("message", ""),
                tool_logs=tool_logs,
                all_messages=messages,
            )
            result["prompt_version"] = final_response.get("prompt_version") or self.prompt_version

            # Cleanup appointments created during this scenario to keep suite reproducible
            self._cleanup_scenario(conversation_id, tool_logs)
            return result

    def _cleanup_scenario(self, conversation_id: str, tool_logs: list[dict]) -> None:
        appt_ids = [
            t["output"].get("appointment_id")
            for t in tool_logs
            if t["tool"] == "book_appointment" and t["output"].get("appointment_id")
        ]
        for appt_id in appt_ids:
            appt = Appointment.objects.filter(id=appt_id).select_related("slot").first()
            if not appt:
                continue
            slot_id = appt.slot_id
            appt.delete()
            AppointmentSlot.objects.filter(id=slot_id).update(is_available=True)
        Conversation.objects.filter(id=conversation_id).delete()

    def _summarize(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        passed = sum(1 for r in results if r["passed"])
        failed = len(results) - passed
        avg = round(sum(r["score"] for r in results) / len(results), 1) if results else 0.0
        return {
            "prompt_version": self.prompt_version or (results[0].get("prompt_version") if results else None),
            "passed": passed,
            "failed": failed,
            "total": len(results),
            "score": avg,
            "results": results,
            "failures": [r for r in results if not r["passed"]],
        }
