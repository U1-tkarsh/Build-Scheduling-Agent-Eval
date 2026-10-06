from __future__ import annotations

from typing import Any


def analyze_failures(eval_summary: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert failed scenarios into structured improvement candidates."""
    improvements: list[dict[str, Any]] = []
    for failure_result in eval_summary.get("failures") or []:
        failure = failure_result.get("failure") or {}
        scenario_id = failure_result["scenario_id"]
        category = failure.get("category") or "task_failure"

        if category == "tool_result_handling" or scenario_id == "booking_tool_failure":
            improvements.append(
                {
                    "failure_id": scenario_id,
                    "category": "tool_result_handling",
                    "root_cause": (
                        "The prompt allows the model to assume booking success after calling the tool."
                    ),
                    "proposed_change": (
                        "Require explicit verification of tool success before confirming an appointment."
                    ),
                    "policy_rule": (
                        "Never tell the patient an appointment is confirmed unless "
                        "book_appointment returned success=true and an appointment_id."
                    ),
                    "target_prompt_version": "v2",
                }
            )
        elif category == "unavailable_slot":
            improvements.append(
                {
                    "failure_id": scenario_id,
                    "category": "unavailable_slot",
                    "root_cause": "Weak handling when requested time is unavailable.",
                    "proposed_change": "Require offering only real alternatives from search_available_slots.",
                    "policy_rule": (
                        "If the requested time is unavailable, say so clearly and offer only "
                        "slots returned by search_available_slots. Never invent times."
                    ),
                    "target_prompt_version": "next",
                }
            )
        else:
            improvements.append(
                {
                    "failure_id": scenario_id,
                    "category": category,
                    "root_cause": failure.get("message") or "Scenario failed deterministic checks.",
                    "proposed_change": "Add a focused policy rule addressing this failure.",
                    "policy_rule": failure.get("message") or "Follow tool results and safety rules strictly.",
                    "target_prompt_version": "next",
                }
            )
    return improvements
