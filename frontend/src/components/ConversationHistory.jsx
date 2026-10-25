export default function ConversationHistory({ turns, onClear }) {
  return (
    <section className="history">
      <div className="history-head">
        <span className="answer-label">Earlier in this conversation</span>
        <button className="ghost" onClick={onClear}>
          New conversation
        </button>
      </div>
      <ol className="history-list">
        {turns.map((turn, index) => (
          <li key={index}>
            <p className="history-question">{turn.question}</p>
            <p className="history-answer">{turn.answer.replace(/\s*\[\d+\]/g, "")}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
