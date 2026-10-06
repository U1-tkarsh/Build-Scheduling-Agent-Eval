from agent.llm import OpenAILLMClient


def test_normalize_preserves_thought_signature():
    client = OpenAILLMClient(
        api_key="test-key",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
    )
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "name": "search_available_slots",
                    "arguments": {"specialty": "dermatology"},
                    "extra_content": {
                        "google": {"thought_signature": "SIG123"}
                    },
                }
            ],
        },
        {
            "role": "tool",
            "name": "search_available_slots",
            "tool_call_id": "call_1",
            "content": '{"success": true, "slots": []}',
        },
    ]
    normalized = client._normalize_messages(messages)
    assert normalized[0]["tool_calls"][0]["extra_content"]["google"]["thought_signature"] == "SIG123"


def test_normalize_adds_skip_signature_when_missing_for_gemini():
    client = OpenAILLMClient(
        api_key="test-key",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
    )
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "name": "search_available_slots",
                    "arguments": {"specialty": "dermatology"},
                }
            ],
        }
    ]
    normalized = client._normalize_messages(messages)
    assert (
        normalized[0]["tool_calls"][0]["extra_content"]["google"]["thought_signature"]
        == "skip_thought_signature_validator"
    )
