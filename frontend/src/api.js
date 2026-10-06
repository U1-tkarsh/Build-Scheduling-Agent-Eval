const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000/api";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    try {
      const data = JSON.parse(text);
      throw new Error(data.error || data.detail || text || `Request failed: ${response.status}`);
    } catch (err) {
      if (err instanceof Error && err.message && !err.message.startsWith("{")) {
        throw err;
      }
      throw new Error(text || `Request failed: ${response.status}`);
    }
  }
  return response.json();
}

export function sendChat({ conversationId, message, promptVersion }) {
  return request("/chat/", {
    method: "POST",
    body: JSON.stringify({
      conversation_id: conversationId,
      message,
      prompt_version: promptVersion || undefined,
    }),
  });
}

export function resetConversation(conversationId) {
  return request("/conversations/reset/", {
    method: "POST",
    body: JSON.stringify({ conversation_id: conversationId }),
  });
}

export function runEvals({ improve = false, promptVersion } = {}) {
  return request("/evals/run/", {
    method: "POST",
    body: JSON.stringify({
      improve,
      prompt_version: promptVersion || undefined,
    }),
  });
}

export function listPrompts() {
  return request("/prompts/");
}
