import MessageBubble from "./MessageBubble";

export default function ChatWindow({ messages, input, setInput, onSend, onReset, busy }) {
  return (
    <section className="panel chat-panel">
      <div className="panel-header">
        <h2>Conversation</h2>
        <button type="button" className="secondary" onClick={onReset} disabled={busy}>
          Reset
        </button>
      </div>
      <div className="messages">
        {messages.length === 0 && (
          <p className="muted">
            Try: “I need a dermatologist next Tuesday afternoon.”
          </p>
        )}
        {messages.map((m, idx) => (
          <MessageBubble key={idx} role={m.role} content={m.content} />
        ))}
      </div>
      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          onSend();
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Patient message"
          disabled={busy}
        />
        <button type="submit" disabled={busy || !input.trim()}>
          Send
        </button>
      </form>
    </section>
  );
}
