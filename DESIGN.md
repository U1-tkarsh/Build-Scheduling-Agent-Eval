# Design Note

## Architecture

Django + React keeps a clear boundary: the UI is a thin demo surface, while scheduling truth lives in Python tools and SQLite. The agent orchestrates prompts, conversation state, and tool calls without a heavy agent framework.

## Safety

Emergency and diagnosis handling are deterministic keyword/pattern checks that run before the LLM. Slot availability and booking confirmation are tool/DB results. Prompts guide tone and clarification; they do not own safety-critical facts.

## Evaluation

Ten fixed scenarios drive multi-turn conversations. Scoring is mostly deterministic: tool logs, appointment rows, and response pattern checks. Transcript-only success is never enough when DB state disagrees.

## Self-Improvement Loop

Failed scenarios become structured improvement objects. The improver appends a focused policy rule and writes a new prompt version. The full suite reruns; the candidate is accepted only if score improves, safety does not regress, and previously passing scenarios still pass.

## Before vs After

- v1 score: ~96 (fails `booking_tool_failure`)
- v2 score: 100
- regressions: 0

## Production Changes

HIPAA review, patient auth, EHR/FHIR integration, audit logs, RBAC, encryption, human escalation, observability, stronger emergency classifiers, and clinician-approved policy governance.

## AI Assistance vs Engineering Judgment

AI accelerated scaffolding. Human judgment kept truth outside the LLM, bounded self-improvement to prompts only, and required regression gates before promotion.
