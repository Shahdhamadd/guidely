import { useState } from "react";

export default function UploadForm({ busy, categories, onUpload }) {
  const [file, setFile] = useState(null);
  const [category, setCategory] = useState("");
  const [dragging, setDragging] = useState(false);

  function handleDragOver(event) {
    event.preventDefault();
    setDragging(true);
  }

  function handleDrop(event) {
    event.preventDefault();
    setDragging(false);
    setFile(event.dataTransfer.files[0] || null);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const form = event.target;
    if (await onUpload(file, category)) {
      // Clear the form so the same file isn't uploaded again by mistake.
      form.reset();
      setFile(null);
      setCategory("");
    }
  }

  return (
    <section className="panel">
      <h2 className="section-title">Add a document</h2>
      <form className="upload-form" onSubmit={handleSubmit}>
        <label
          className={dragging ? "dropzone dragging" : "dropzone"}
          onDragOver={handleDragOver}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
        >
          <input type="file" accept=".txt,.md,.pdf" onChange={(event) => setFile(event.target.files[0] || null)} />
          <svg className="dropzone-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M12 16V4m0 0-4 4m4-4 4 4" />
            <path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" />
          </svg>
          <span className="dropzone-title">{file ? file.name : "Drop a file here, or click to choose"}</span>
          <span className="dropzone-hint">.txt, .md or .pdf · up to 5 MB · start each section with a "# Heading" line</span>
        </label>

        <div className="upload-row">
          <input
            className="field"
            list="category-options"
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            placeholder="Category (optional, defaults to General)"
          />
          <datalist id="category-options">
            {categories.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
          <button type="submit" className="primary" disabled={busy || !file}>
            Upload
          </button>
        </div>
      </form>
    </section>
  );
}
