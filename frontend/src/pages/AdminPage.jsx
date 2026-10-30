import { useEffect, useState } from "react";
import {
  QUERY_LOG_CSV_URL,
  deleteDocument,
  getDocument,
  getDocuments,
  reindexDocuments,
  saveDocument,
  setDocumentCategory,
  uploadDocument,
} from "../api";
import DocumentEditor from "../components/DocumentEditor";
import DocumentList from "../components/DocumentList";
import ErrorMessage from "../components/ErrorMessage";
import IndexReport from "../components/IndexReport";
import UploadForm from "../components/UploadForm";

export default function AdminPage() {
  const [documents, setDocuments] = useState([]);
  const [categories, setCategories] = useState([]);
  const [editing, setEditing] = useState(null);
  const [report, setReport] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    run(loadDocuments);
  }, []);

  async function loadDocuments() {
    const data = await getDocuments();
    setDocuments(data.documents);
    setCategories(data.categories || []);
  }

  // Returns true if the action worked, so a form can clear itself.
  async function run(action) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await action();
      return true;
    } catch (err) {
      setError(err.message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  function handleUpload(file, category) {
    return run(async () => {
      const data = await uploadDocument(file, category);
      setMessage(data.message);
      setReport(data.index);
      await loadDocuments();
    });
  }

  function handleEdit(name) {
    run(async () => {
      const data = await getDocument(name);
      setEditing(data);
    });
  }

  function handleSave(text) {
    run(async () => {
      const data = await saveDocument(editing.name, text);
      setMessage(data.message);
      setReport(data.index);
      setEditing(null);
    });
  }

  function handleDelete(name) {
    if (!window.confirm(`Delete ${name}? This cannot be undone.`)) {
      return;
    }
    run(async () => {
      const data = await deleteDocument(name);
      setMessage(data.message);
      setReport(data.index);
      await loadDocuments();
    });
  }

  function handleCategory(name, category) {
    run(async () => {
      const data = await setDocumentCategory(name, category);
      setMessage(data.message);
      await loadDocuments();
    });
  }

  function handleReindex() {
    run(async () => {
      const data = await reindexDocuments();
      setMessage("Re-index finished.");
      setReport(data);
    });
  }

  return (
    <div className="admin-page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Documents</h1>
          <p className="page-text">Everything Guidely answers from. Uploads, edits and deletes are re-indexed for you.</p>
        </div>
        <div className="page-actions">
          <a className="secondary" href={QUERY_LOG_CSV_URL} download>
            Export query log (CSV)
          </a>
          <button className="secondary" onClick={handleReindex} disabled={busy}>
            {busy ? "Working…" : "Re-index all"}
          </button>
        </div>
      </div>

      {error && <ErrorMessage message={error} />}
      {message && (
        <div className="notice success" role="status">
          <span className="notice-icon">✓</span>
          <span>{message}</span>
        </div>
      )}

      {report && <IndexReport report={report} />}

      {editing ? (
        <DocumentEditor
          name={editing.name}
          initialText={editing.text}
          busy={busy}
          onSave={handleSave}
          onCancel={() => setEditing(null)}
        />
      ) : (
        <>
          <UploadForm busy={busy} categories={categories} onUpload={handleUpload} />
          <DocumentList
            documents={documents}
            categories={categories}
            busy={busy}
            onEdit={handleEdit}
            onDelete={handleDelete}
            onCategory={handleCategory}
          />
        </>
      )}
    </div>
  );
}
