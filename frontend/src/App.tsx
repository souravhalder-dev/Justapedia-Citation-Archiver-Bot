import { useEffect, useState } from "react";
import { Header } from "./components/Header";
import { LoginView } from "./components/LoginView";
import { ArticleScanner } from "./components/ArticleScanner";
import { AutoModePanel } from "./components/AutoModePanel";
import { VersionHistory } from "./components/VersionHistory";
import { UrlTester } from "./components/UrlTester";
import { JobHistory } from "./components/JobHistory";
import type { SystemStatus, UserSession } from "./types";
import { Search, Zap, History, Link2, FileText, Code2, Mail } from "lucide-react";

export function App() {
  const [user, setUser] = useState<UserSession | null>(() => {
    const saved = localStorage.getItem("justapedia_user");
    return saved ? JSON.parse(saved) : null;
  });
  const [activeTab, setActiveTab] = useState<"scan" | "auto" | "versions" | "tester" | "history">("auto");
  const [status, setStatus] = useState<SystemStatus | null>(null);

  const fetchStatus = async () => {
    try {
      const res = await fetch("/api/status");
      if (res.ok) {
        const data: SystemStatus = await res.json();
        setStatus(data);
      }
    } catch (err) {
      console.error("Failed to connect to backend API", err);
    }
  };

  const handleLogout = async () => {
    if (user?.token) {
      try {
        await fetch("/api/auth/logout", {
          method: "POST",
          headers: { Authorization: `Bearer ${user.token}` },
        });
      } catch (err) {
        console.error(err);
      }
    }
    localStorage.removeItem("justapedia_token");
    localStorage.removeItem("justapedia_user");
    setUser(null);
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  // Require Authentication: If not logged in, render login view (Requirement 5)
  if (!user) {
    return (
      <div className="app-container">
        <LoginView onLoginSuccess={(u) => setUser(u)} />
        {/* Developer Footer */}
        <footer
          style={{
            marginTop: "3rem",
            paddingTop: "1.5rem",
            borderTop: "1px solid var(--border-color)",
            textAlign: "center",
            fontSize: "0.85rem",
            color: "var(--text-muted)",
          }}
        >
          <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: "1.5rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem" }}>
              <Code2 size={15} color="#38bdf8" /> Developer: <strong>Sourav Halder</strong>
            </span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem" }}>
              <Mail size={15} color="#38bdf8" /> Email: <strong>skhsouravhalder@gmail.com</strong>
            </span>
          </div>
          <div>Justapedia Wayback Machine Citation Archiver Bot &bull; Production v2.0</div>
        </footer>
      </div>
    );
  }

  return (
    <div className="app-container">
      <Header status={status} user={user} onLogout={handleLogout} />

      {/* Tabs navigation - Settings option removed (Requirement 8) */}
      <nav className="tabs-nav">
        <button
          className={`tab-btn ${activeTab === "auto" ? "active" : ""}`}
          onClick={() => setActiveTab("auto")}
        >
          <Zap size={18} /> Automatic Mode
        </button>
        <button
          className={`tab-btn ${activeTab === "scan" ? "active" : ""}`}
          onClick={() => setActiveTab("scan")}
        >
          <Search size={18} /> Manual Archiver
        </button>
        <button
          className={`tab-btn ${activeTab === "versions" ? "active" : ""}`}
          onClick={() => setActiveTab("versions")}
        >
          <History size={18} /> Version History
        </button>
        <button
          className={`tab-btn ${activeTab === "tester" ? "active" : ""}`}
          onClick={() => setActiveTab("tester")}
        >
          <Link2 size={18} /> URL Inspector
        </button>
        <button
          className={`tab-btn ${activeTab === "history" ? "active" : ""}`}
          onClick={() => setActiveTab("history")}
        >
          <FileText size={18} /> Job History
        </button>
      </nav>

      {/* Main Tab Content */}
      <main>
        {activeTab === "auto" && <AutoModePanel user={user} />}
        {activeTab === "scan" && <ArticleScanner user={user} />}
        {activeTab === "versions" && <VersionHistory user={user} />}
        {activeTab === "tester" && <UrlTester user={user} />}
        {activeTab === "history" && <JobHistory user={user} />}
      </main>

      {/* Developer Information Footer (Requirement 9) */}
      <footer
        style={{
          marginTop: "3rem",
          paddingTop: "1.5rem",
          borderTop: "1px solid var(--border-color)",
          textAlign: "center",
          fontSize: "0.85rem",
          color: "var(--text-muted)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: "1.5rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem" }}>
            <Code2 size={15} color="#38bdf8" /> Developer: <strong>Sourav Halder</strong>
          </span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem" }}>
            <Mail size={15} color="#38bdf8" /> Email: <strong>skhsouravhalder@gmail.com</strong>
          </span>
        </div>
        <div>Justapedia Wayback Machine Citation Archiver Bot &bull; Production v2.0</div>
      </footer>
    </div>
  );
}

export default App;
