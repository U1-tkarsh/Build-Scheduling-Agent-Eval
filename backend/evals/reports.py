from __future__ import annotations

from typing import Any


def format_run_console(summary: dict[str, Any]) -> str:
    version = summary.get("prompt_version") or "?"
    lines = [f"Running evaluation suite against prompt {version}", ""]
    for result in summary.get("results") or []:
        status = "PASS" if result["passed"] else "FAIL"
        lines.append(f"{status} {result['scenario_id']:<28} {result['score']}")
    lines.append("")
    lines.append(f"Overall: {summary.get('score')}")
    return "\n".join(lines)


def format_improvement_console(loop_result: dict[str, Any]) -> str:
    lines = [format_run_console(loop_result["baseline"]), ""]

    failures = loop_result["baseline"].get("failures") or []
    if failures:
        lines.append("Failure detected:")
        for f in failures:
            lines.append(f"  {f['scenario_id']}")
        lines.append("")

    improvement = loop_result.get("improvement") or {}
    if improvement.get("applied"):
        primary = improvement.get("primary") or {}
        lines.append("Generated improvement:")
        lines.append(f"  {primary.get('policy_rule')}")
        lines.append("")
        lines.append(f"Created prompt version: {improvement.get('new_version')}")
        lines.append("")
        lines.append("Re-running full suite...")
        lines.append("")
        if loop_result.get("rerun"):
            lines.append(format_run_console(loop_result["rerun"]))
            decision = loop_result.get("decision") or {}
            lines.append("")
            lines.append(f"Regression count: {len(decision.get('regressions') or [])}")
            lines.append("")
            if decision.get("accepted"):
                lines.append(f"{improvement.get('new_version')} accepted.")
            else:
                lines.append(f"Rejected: {decision.get('reason')}")
    else:
        lines.append(improvement.get("reason") or "No improvement applied.")

    return "\n".join(lines)
