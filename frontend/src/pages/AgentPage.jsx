import { useState } from "react";
import ChatWindow from "../components/ChatWindow";
import StatePanel from "../components/StatePanel";
import { resetConversation, sendChat } from "../api";

export default function AgentPage() {
  const [conversationId, setConversationId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [state, setState] = useState({});
  const [promptVersion, setPromptVersion] = useState(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function handleSend() {
    const text = input.trim();
    if (!text) return;
    setBusy(true);
    setError("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    try {
      const result = await sendChat({ conversationId, message: text });
      setConversationId(result.conversation_id);
      setState(result.state || {});
      setPromptVersion(result.prompt_version);
      setMessages((prev) => [...prev, { role: "assistant", content: result.message }]);
    } catch (err) {
      setError(err.message || "Chat request failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleReset() {
    setBusy(true);
    setError("");
    try {
      const result = await resetConversation(conversationId);
      setConversationId(result.conversation_id);
      setState(result.state || {});
      setMessages([]);
    } catch (err) {
      setError(err.message || "Reset failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <h1>Self-Improving Scheduling Agent</h1>
        <p>Multi-turn booking with backend tools and structured state.</p>
      </header>
      {error && <p className="error">{error}</p>}
      <div className="agent-layout">
        <ChatWindow
          messages={messages}
          input={input}
          setInput={setInput}
          onSend={handleSend}
          onReset={handleReset}
          busy={busy}
        />
        <StatePanel state={state} promptVersion={promptVersion} />
      </div>
    </div>
  );
}
