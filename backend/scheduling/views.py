from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from agent.prompt_manager import PromptManager
from agent.service import SchedulingAgent
from evals.improver import run_improvement_loop
from evals.runner import EvalRunner
from scheduling.models import Conversation, PromptVersion


@api_view(["POST"])
def chat(request):
    conversation_id = request.data.get("conversation_id")
    message = (request.data.get("message") or "").strip()
    if not message:
        return Response({"error": "message is required"}, status=status.HTTP_400_BAD_REQUEST)

    prompt_version = request.data.get("prompt_version")
    try:
        agent = SchedulingAgent(prompt_version=prompt_version)
        result = agent.handle_message(conversation_id, message)
    except RuntimeError as exc:
        err = str(exc)
        code = status.HTTP_502_BAD_GATEWAY
        if "401" in err or "UNAUTHENTICATED" in err:
            code = status.HTTP_401_UNAUTHORIZED
            err = (
                "Gemini authentication failed. Check LLM_API_KEY in backend/.env "
                "(use an API key from https://aistudio.google.com/apikey) and restart the server."
            )
        elif "429" in err or "RESOURCE_EXHAUSTED" in err:
            code = status.HTTP_429_TOO_MANY_REQUESTS
            err = (
                "Gemini quota exceeded. Wait a minute, or set USE_FAKE_LLM=true in backend/.env "
                "for offline chat. Evals always use FakeLLM and do not consume quota."
            )
        elif "503" in err or "UNAVAILABLE" in err:
            code = status.HTTP_503_SERVICE_UNAVAILABLE
            err = "Gemini is temporarily unavailable (high demand). Please try again in a moment."
        elif "400" in err and "thought_signature" in err:
            err = (
                "Gemini tool-calling signature error. Restart the server after the latest "
                "backend update, then start a new conversation (Reset)."
            )
        return Response({"error": err}, status=code)

    return Response(
        {
            "conversation_id": result["conversation_id"],
            "message": result["message"],
            "state": result["state"],
            "tool_logs": result.get("tool_logs", []),
            "prompt_version": result.get("prompt_version"),
        }
    )


@api_view(["POST"])
def reset_conversation(request):
    conversation_id = request.data.get("conversation_id")
    agent = SchedulingAgent()
    result = agent.reset_conversation(conversation_id)
    return Response(result)


@api_view(["GET"])
def get_conversation(request, conversation_id: str):
    try:
        conversation = Conversation.objects.get(id=conversation_id)
    except Conversation.DoesNotExist:
        return Response({"error": "not found"}, status=status.HTTP_404_NOT_FOUND)
    return Response(
        {
            "conversation_id": conversation.id,
            "state": conversation.state_json,
            "messages": conversation.messages_json,
            "tool_logs": conversation.tool_logs_json,
        }
    )


@api_view(["POST"])
def run_evals_api(request):
    from django.conf import settings

    # Never burn Gemini quota on the evaluation dashboard
    settings.USE_FAKE_LLM = True

    improve = bool(request.data.get("improve", False))
    prompt_version = request.data.get("prompt_version") or PromptManager().get_active_version()

    if improve:
        loop_result = run_improvement_loop(prompt_version=prompt_version)
        return Response(loop_result)

    summary = EvalRunner(prompt_version=prompt_version).run_all()
    return Response(summary)


@api_view(["GET"])
def prompt_versions(request):
    pm = PromptManager()
    versions = []
    for version in pm.list_versions():
        db = PromptVersion.objects.filter(version=version).first()
        versions.append(
            {
                "version": version,
                "is_active": db.is_active if db else version == pm.get_active_version(),
                "score": db.score if db else None,
                "accepted": db.accepted if db else False,
            }
        )
    return Response({"versions": versions, "active": pm.get_active_version()})
