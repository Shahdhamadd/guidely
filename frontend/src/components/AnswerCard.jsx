export default function AnswerCard({ answer, latencyMs }) {
  const parts = answer.split(/(\[\d+\])/);

  return (
    <section className="answer-card">
      <div className="answer-label">Answer</div>
      <p className="answer">
        {parts.map((part, index) => {
          const match = part.match(/^\[(\d+)\]$/);
          if (!match) {
            return part;
          }
          return (
            <a key={index} className="cite" href={`#source-${match[1]}`} title={`Go to source ${match[1]}`}>
              {match[1]}
            </a>
          );
        })}
      </p>
      {latencyMs === undefined ? (
        <p className="meta pulse">Writing the answer…</p>
      ) : (
        <p className="meta">Answered in {(latencyMs / 1000).toFixed(1)} seconds</p>
      )}
    </section>
  );
}
