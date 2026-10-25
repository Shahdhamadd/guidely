export default function SearchBox({
  question,
  category,
  categories,
  loading,
  placeholder,
  onQuestion,
  onCategory,
  onAsk,
}) {
  function handleSubmit(event) {
    event.preventDefault();
    onAsk();
  }

  return (
    <form className="search-box" onSubmit={handleSubmit}>
      <div className="search-field">
        <svg className="search-icon" viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
        <input
          value={question}
          onChange={(event) => onQuestion(event.target.value)}
          placeholder={placeholder}
          aria-label="Question"
        />
      </div>
      <select
        className="field search-category"
        value={category}
        onChange={(event) => onCategory(event.target.value)}
        aria-label="Category"
      >
        <option value="">All categories</option>
        {categories.map((name) => (
          <option key={name} value={name}>
            {name}
          </option>
        ))}
      </select>
      <button type="submit" className="primary" disabled={loading}>
        {loading ? "Thinking…" : "Ask"}
      </button>
    </form>
  );
}
