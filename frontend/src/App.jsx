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
        {page === "search" && <SearchPage />}
        {page === "admin" && <AdminPage />}
      </main>
    </div>
  );
}
