const NEW_CATEGORY = "__new__";

export default function DocumentList({ documents, categories, busy, onEdit, onDelete, onCategory }) {
  function handleCategoryChange(name, value) {
    if (value === NEW_CATEGORY) {
      const newName = window.prompt("Name of the new category:");
      if (newName && newName.trim()) {
        onCategory(name, newName.trim());
      }
      return;
    }
    onCategory(name, value);
  }

  return (
    <section className="panel">
      <h2 className="section-title">
        Library <span className="count">{documents.length}</span>
      </h2>

      {documents.length === 0 && <p className="empty">No documents yet. Upload one above to get started.</p>}

      <ul className="document-list">
        {documents.map((document) => {
          const extension = document.name.split(".").pop();
          return (
            <li key={document.name}>
              <span className={`file-badge ${extension}`}>{extension}</span>
              <span className="document-name">{document.name}</span>
              <select
                className="field small"
                value={document.category}
                disabled={busy}
                onChange={(event) => handleCategoryChange(document.name, event.target.value)}
                aria-label={`Category of ${document.name}`}
              >
                {categories.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
                <option value={NEW_CATEGORY}>+ New category…</option>
              </select>
              <div className="row-buttons">
                {extension !== "pdf" && (
                  <button className="ghost" onClick={() => onEdit(document.name)} disabled={busy}>
                    Edit
                  </button>
                )}
                <button className="ghost danger" onClick={() => onDelete(document.name)} disabled={busy}>
                  Delete
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
