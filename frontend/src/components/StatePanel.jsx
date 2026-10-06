function formatValue(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.length ? JSON.stringify(value) : "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export default function StatePanel({ state, promptVersion }) {
  const fields = [
    ["Patient", state?.patient_name],
    ["Specialty", state?.specialty],
    ["Date", state?.preferred_date],
    ["Time preference", state?.preferred_time],
    ["Selected slot", state?.selected_slot_id],
    ["Appointment ID", state?.appointment_id],
    ["Status", state?.status],
  ];

  return (
    <section className="panel state-panel">
      <div className="panel-header">
        <h2>Conversation State</h2>
        <span className="badge">Prompt {promptVersion || "—"}</span>
      </div>
      <dl className="state-grid">
        {fields.map(([label, value]) => (
          <div key={label} className="state-row">
            <dt>{label}</dt>
            <dd>{formatValue(value)}</dd>
          </div>
        ))}
      </dl>
      {!!state?.last_search_slots?.length && (
        <div className="slot-list">
          <h3>Last search results</h3>
          <ul>
            {state.last_search_slots.map((slot) => (
              <li key={slot.slot_id}>
                #{slot.slot_id} · {slot.doctor} · {slot.start_time}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
