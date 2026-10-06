from __future__ import annotations

from typing import Any

from agent.prompt_manager import PromptManager
from evals.failure_analyzer import analyze_failures
from evals.runner import EvalRunner


BOOKING_RULE_BLOCK = """
BOOKING VERIFICATION:
Never state that an appointment is booked, confirmed, or scheduled unless
the book_appointment tool returned success=true and a valid appointment_id.
If the tool fails, clearly say the booking was not completed.
""".strip()


class PromptImprover:
    """Apply small, auditable policy additions — never rewrite the whole prompt."""

    def __init__(self):
        self.prompt_manager = PromptManager()

    def improve_from_eval(self, baseline: dict[str, Any]) -> dict[str, Any]:
        improvements = analyze_failures(baseline)
        if not improvements:
            return {
                "applied": False,
                "reason": "No failures to improve from.",
                "improvements": [],
            }

        # Prefer the booking verification improvement when present
        primary = next(
            (i for i in improvements if i["category"] == "tool_result_handling"),
            improvements[0],
        )

        current_version = baseline.get("prompt_version") or self.prompt_manager.get_active_version()
        current_prompt = self.prompt_manager.read_file(current_version)

        if primary["policy_rule"].lower() in current_prompt.lower() or (
            "BOOKING VERIFICATION" in current_prompt
            and primary["category"] == "tool_result_handling"
        ):
            return {
                "applied": False,
                "reason": "Policy rule already present in active prompt.",
                "improvements": improvements,
                "current_version": current_version,
            }

        new_version = self.prompt_manager.next_version_name()
        # If v2 file already has our known fix and current is v1, use that content
        if current_version == "v1" and primary["category"] == "tool_result_handling":
            try:
                candidate = self.prompt_manager.read_file("v2")
                if "BOOKING VERIFICATION" in candidate:
                    new_content = candidate
                    new_version = "v2"
                else:
                    new_content = current_prompt.rstrip() + "\n\n" + BOOKING_RULE_BLOCK + "\n"
            except FileNotFoundError:
                new_content = current_prompt.rstrip() + "\n\n" + BOOKING_RULE_BLOCK + "\n"
        else:
            new_content = current_prompt.rstrip() + "\n\n" + primary["policy_rule"] + "\n"

        primary["target_prompt_version"] = new_version
        self.prompt_manager.save_version(
            new_version,
            new_content,
            activate=False,
            notes=f"Generated from failure {primary['failure_id']}",
        )

        return {
            "applied": True,
            "improvements": improvements,
            "primary": primary,
            "new_version": new_version,
            "previous_version": current_version,
        }

    def accept_if_better(
        self,
        *,
        old_summary: dict[str, Any],
        new_summary: dict[str, Any],
        new_version: str,
    ) -> dict[str, Any]:
        old_score = old_summary["score"]
        new_score = new_summary["score"]

        old_pass_ids = {r["scenario_id"] for r in old_summary["results"] if r["passed"]}
        new_pass_ids = {r["scenario_id"] for r in new_summary["results"] if r["passed"]}
        regressions = sorted(old_pass_ids - new_pass_ids)

        # Critical safety scenarios must not regress
        safety_ids = {"emergency_case", "no_diagnosis"}
        safety_regression = any(
            r["scenario_id"] in safety_ids and not r["passed"] for r in new_summary["results"]
        ) and any(
            r["scenario_id"] in safety_ids and r["passed"] for r in old_summary["results"]
        )

        accept = new_score > old_score and not regressions and not safety_regression

        if accept:
            self.prompt_manager.save_version(
                new_version,
                self.prompt_manager.read_file(new_version),
                activate=True,
                score=new_score,
                accepted=True,
                notes=f"+{round(new_score - old_score, 1)} points, regressions={len(regressions)}",
            )
            # Keep previous score recorded
            self.prompt_manager.save_version(
                old_summary.get("prompt_version") or "v1",
                self.prompt_manager.read_file(old_summary.get("prompt_version") or "v1"),
                activate=False,
                score=old_score,
                accepted=False,
            )
            reason = f"+{round(new_score - old_score, 1)} points, no regressions"
        else:
            reason = "Rejected: score did not improve, or regressions/safety issues detected."
            if regressions:
                reason += f" Regressions: {regressions}."
            # Ensure old remains active
            old_v = old_summary.get("prompt_version") or self.prompt_manager.get_active_version()
            self.prompt_manager.set_active(old_v)

        return {
            "accepted": accept,
            "reason": reason,
            "old_score": old_score,
            "new_score": new_score,
            "regressions": regressions,
            "new_version": new_version,
        }


def run_improvement_loop(prompt_version: str = "v1") -> dict[str, Any]:
    """Baseline -> improve -> rerun -> accept/reject."""
    # Ensure starting version is active
    pm = PromptManager()
    pm.set_active(prompt_version)

    baseline_runner = EvalRunner(prompt_version=prompt_version)
    baseline = baseline_runner.run_all()
    baseline["prompt_version"] = prompt_version

    improver = PromptImprover()
    improvement = improver.improve_from_eval(baseline)

    if not improvement.get("applied"):
        return {
            "baseline": baseline,
            "improvement": improvement,
            "rerun": None,
            "decision": {"accepted": False, "reason": improvement.get("reason")},
        }

    new_version = improvement["new_version"]
    rerun = EvalRunner(prompt_version=new_version).run_all()
    rerun["prompt_version"] = new_version

    decision = improver.accept_if_better(
        old_summary=baseline,
        new_summary=rerun,
        new_version=new_version,
    )

    return {
        "baseline": baseline,
        "improvement": improvement,
        "rerun": rerun,
        "decision": decision,
    }
