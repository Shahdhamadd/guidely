import { useState } from "react";

export default function DocumentEditor({ name, initialText, busy, onSave, onCancel }) {
  const [text, setText] = useState(initialText);

  return (
    <section className="panel">
      <div className="panel-head">
        <h2 className="section-title">Editing {name}</h2>
        <span className="meta">Each "# Heading" line starts a new section</span>
      </div>

      <textarea className="editor" value={text} onChange={(event) => setText(event.target.value)} rows={18} />

      <div className="buttons">
        <button className="primary" onClick={() => onSave(text)} disabled={busy}>
          {busy ? "Saving…" : "Save and re-index"}
        </button>
        <button className="secondary" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
      </div>
    </section>
  );
}
