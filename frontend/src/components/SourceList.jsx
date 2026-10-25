export default function SourceList({ sources }) {
  return (
    <section className="sources">
      <h2 className="section-title">
        Sources <span className="count">{sources.length}</span>
      </h2>

      {sources.map((source) => {
        const match = Math.round(source.score * 100);
        return (
          <article key={source.id} id={`source-${source.id}`} className="source">
            <div className="source-head">
              <span className="source-number">{source.id}</span>
              <div className="source-title">
                <strong>{source.section}</strong>
                <span>{source.file}</span>
              </div>
              <span className="tag">{source.category}</span>
            </div>

            <blockquote>{source.snippet}</blockquote>

            <div className="match">
              <div className="match-bar">
                <span style={{ width: `${match}%` }} />
              </div>
              {match}% match
            </div>

            <details>
              <summary>Show full passage</summary>
              <p>{source.text}</p>
            </details>
          </article>
        );
      })}
    </section>
  );
}
