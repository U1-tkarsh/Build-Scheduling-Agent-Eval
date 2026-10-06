export default function MessageBubble({ role, content }) {
  const isUser = role === "user";
  return (
    <div className={`bubble ${isUser ? "bubble-user" : "bubble-agent"}`}>
      <div className="bubble-role">{isUser ? "Patient" : "Agent"}</div>
      <div className="bubble-content">{content}</div>
    </div>
  );
}
