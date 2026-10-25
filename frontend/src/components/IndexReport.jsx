import ErrorMessage from "./ErrorMessage";

export default function IndexReport({ report }) {
  const stats = [
    ["Files indexed", report.files_indexed],
    ["Unchanged", report.files_unchanged],
    ["Chunks", report.chunks],
    ["New embeddings", report.new_embeddings],
    ["From cache", report.cache_hits],
    ["Removed", report.embeddings_removed],
  ];

  return (
    <section className="panel">
      <div className="panel-head">
        <h2 className="section-title">Last index run</h2>
        <span className="meta">{report.seconds} seconds</span>
      </div>

      <div className="stats">
        {stats.map(([label, value]) => (
          <div key={label} className="stat">
            <span className="stat-value">{value}</span>
            <span className="stat-label">{label}</span>
          </div>
        ))}
      </div>

      {report.files_failed.length > 0 && (
        <ErrorMessage message={"Skipped files: " + report.files_failed.join(", ")} />
      )}
    </section>
  );
}
