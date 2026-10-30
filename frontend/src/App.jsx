import { useState } from "react";
import AdminPage from "./pages/AdminPage";
import SearchPage from "./pages/SearchPage";

export default function App() {
  const [page, setPage] = useState("search");

  return (
    <div className="app">
      <header className="topbar">
        <button className="brand" onClick={() => setPage("search")}>
          <span className="brand-mark">G</span>
          <span className="brand-name">Guidely</span>
        </button>
        <nav className="tabs">
          <button className={page === "search" ? "tab active" : "tab"} onClick={() => setPage("search")}>
            Ask
          </button>
          <button className={page === "admin" ? "tab active" : "tab"} onClick={() => setPage("admin")}>
            Documents
          </button>
        </nav>
      </header>

      <main>
        {/* The Ask page is hidden, not removed, so the conversation survives a visit to Documents. */}
        <div hidden={page !== "search"}>
          <SearchPage active={page === "search"} />
        </div>
        {page === "admin" && <AdminPage />}
      </main>
    </div>
  );
}
