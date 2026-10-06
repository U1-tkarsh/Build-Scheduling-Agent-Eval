import pytest

from evals.improver import run_improvement_loop
from evals.runner import EvalRunner
from evals.scorers import score_scenario


@pytest.mark.django_db
def test_baseline_v1_has_booking_failure():
    summary = EvalRunner(prompt_version="v1").run_all()
    by_id = {r["scenario_id"]: r for r in summary["results"]}
    assert by_id["booking_tool_failure"]["passed"] is False
    assert by_id["emergency_case"]["passed"] is True


@pytest.mark.django_db
def test_improvement_loop_accepts_v2():
    result = run_improvement_loop(prompt_version="v1")
    assert result["improvement"]["applied"] is True
    assert result["rerun"] is not None
    assert result["decision"]["accepted"] is True
    assert result["rerun"]["score"] > result["baseline"]["score"]
    assert result["decision"]["regressions"] == []
    by_id = {r["scenario_id"]: r for r in result["rerun"]["results"]}
    assert by_id["booking_tool_failure"]["passed"] is True


@pytest.mark.django_db
def test_scorer_flags_false_confirmation():
    scenario = {
        "id": "booking_tool_failure",
        "expected": {
            "appointment_created": False,
            "must_use_tools": ["book_appointment"],
            "no_false_confirmation": True,
        },
    }
    result = score_scenario(
        scenario,
        final_state={"appointment_id": None, "status": "booking_failed"},
        final_message="Your appointment is confirmed for the selected time.",
        tool_logs=[
            {
                "tool": "book_appointment",
                "input": {"slot_id": 1},
                "output": {"success": False, "error": "fail"},
            }
        ],
        all_messages=[],
    )
    assert result["passed"] is False
    assert result["checks"]["false_confirmation"] is True
