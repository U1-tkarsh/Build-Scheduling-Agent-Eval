import { useState } from "react";
import AgentPage from "./pages/AgentPage";
import EvalPage from "./pages/EvalPage";
import "./App.css";

export default function App() {
  const [tab, setTab] = useState("agent");

  return (
    <div className="app-shell">
      <nav className="top-nav">
        <div className="brand">Scheduling Agent Eval</div>
        <div className="tabs">
          <button
            type="button"
            className={tab === "agent" ? "active" : ""}
            onClick={() => setTab("agent")}
          >
            Agent Demo
          </button>
          <button
            type="button"
            className={tab === "eval" ? "active" : ""}
            onClick={() => setTab("eval")}
          >
            Evaluation
          </button>
        </div>
      </nav>
      {tab === "agent" ? <AgentPage /> : <EvalPage />}
    </div>
  );
}
