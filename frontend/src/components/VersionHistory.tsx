import { useEffect, useState } from "react";
import type { FC } from "react";
import { History, GitCommit, User, X, Eye } from "lucide-react";
import type { ArticleVersion, UserSession } from "../types";

interface VersionHistoryProps {
  user: UserSession;
}

export const VersionHistory: FC<VersionHistoryProps> = ({ user }) => {
  const [versions, setVersions] = useState<ArticleVersion[]>([]);
  const [filterTitle, setFilterTitle] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedVersion, setSelectedVersion] = useState<ArticleVersion | null>(null);

  const fetchVersions = async () => {
    setLoading(true);
    try {
      let url = "/api/versions?limit=50";
      if (filterTitle.trim()) {
        url += `&article=${encodeURIComponent(filterTitle.trim())}`;
      }
      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${user.token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setVersions(data);
      }
    } catch (err) {
      console.error("Failed to load article versions", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchVersions();
  }, []);

  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem", flexWrap: "wrap", gap: "0.75rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <History size={22} color="#38bdf8" />
          <h2 style={{ fontSize: "1.2rem", fontWeight: 700 }}>Article Update Version History</h2>
        </div>

        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <input
            type="text"
            value={filterTitle}
            onChange={(e) => setFilterTitle(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && fetchVersions()}
            placeholder="Filter by article title..."
            style={{ width: "240px", padding: "0.45rem 0.75rem", fontSize: "0.85rem" }}
          />
          <button className="btn btn-secondary" onClick={fetchVersions} style={{ padding: "0.45rem 0.85rem", fontSize: "0.85rem" }}>
            Search
          </button>
        </div>
      </div>

      <p style={{ fontSize: "0.875rem", color: "var(--text-muted)", marginBottom: "1.25rem" }}>
        Every revision made by manual scan or Auto Mode is snapshot here. Review changes, tracked parameters, and edit attribution.
      </p>

      {loading ? (
        <p style={{ color: "var(--text-muted)", fontSize: "0.9rem" }}>Loading version history...</p>
      ) : versions.length === 0 ? (
        <div style={{ textAlign: "center", padding: "2rem", color: "var(--text-muted)" }}>
          <GitCommit size={36} style={{ margin: "0 auto 0.75rem", opacity: 0.4 }} />
          <p>No saved article versions found. Run an archiving update to create version snapshots.</p>
        </div>
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Rev ID</th>
                <th>Article Title</th>
                <th>Version</th>
                <th>Operator</th>
                <th>Mode</th>
                <th>Citations Added</th>
                <th>MediaWiki Rev</th>
                <th>Saved At</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {versions.map((ver) => (
                <tr key={ver.id}>
                  <td style={{ fontFamily: "monospace", fontSize: "0.85rem" }}>#{ver.id}</td>
                  <td style={{ fontWeight: 600 }}>{ver.article_title}</td>
                  <td>
                    <span className="badge" style={{ background: "rgba(56, 189, 248, 0.15)", color: "#38bdf8" }}>
                      v{ver.version_num}
                    </span>
                  </td>
                  <td>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: "4px", fontSize: "0.85rem", color: "#38bdf8" }}>
                      <User size={13} /> {ver.username}
                    </span>
                  </td>
                  <td>
                    <span className={`badge ${ver.mode === "live_edit" || ver.mode === "manual_apply" ? "badge-working" : "badge-inconclusive"}`}>
                      {ver.mode}
                    </span>
                  </td>
                  <td style={{ fontWeight: 600, color: "#34d399" }}>+{ver.citations_updated}</td>
                  <td>{ver.mediawiki_revid ? `r${ver.mediawiki_revid}` : "—"}</td>
                  <td style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                    {new Date(ver.created_at).toLocaleString()}
                  </td>
                  <td>
                    <button
                      className="btn btn-secondary"
                      onClick={() => setSelectedVersion(ver)}
                      style={{ padding: "0.3rem 0.65rem", fontSize: "0.8rem", display: "inline-flex", alignItems: "center", gap: "4px" }}
                    >
                      <Eye size={13} /> Diff
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Version Detail Modal */}
      {selectedVersion && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: "rgba(0, 0, 0, 0.8)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
            padding: "1rem",
          }}
        >
          <div
            className="card"
            style={{
              width: "100%",
              maxWidth: "850px",
              background: "#1e293b",
              border: "1px solid var(--border-color)",
              position: "relative",
              maxHeight: "90vh",
              overflowY: "auto",
            }}
          >
            <button
              onClick={() => setSelectedVersion(null)}
              style={{
                position: "absolute",
                top: "1rem",
                right: "1rem",
                background: "transparent",
                border: "none",
                color: "var(--text-muted)",
                cursor: "pointer",
              }}
            >
              <X size={20} />
            </button>

            <h3 style={{ fontSize: "1.1rem", fontWeight: 700, marginBottom: "0.5rem" }}>
              Version {selectedVersion.version_num} for [[{selectedVersion.article_title}]]
            </h3>
            <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginBottom: "1rem" }}>
              Saved on {new Date(selectedVersion.created_at).toLocaleString()} by <strong>{selectedVersion.username}</strong> ({selectedVersion.mode})
            </p>

            <div style={{ marginBottom: "1rem" }}>
              <h4 style={{ fontSize: "0.9rem", fontWeight: 600, marginBottom: "0.4rem" }}>Unified Wikitext Diff:</h4>
              <div className="diff-container" style={{ maxHeight: "350px" }}>
                {selectedVersion.diff ? (
                  selectedVersion.diff.split("\n").map((line, idx) => {
                    let className = "";
                    if (line.startsWith("+") && !line.startsWith("+++")) {
                      className = "diff-add";
                    } else if (line.startsWith("-") && !line.startsWith("---")) {
                      className = "diff-del";
                    } else if (line.startsWith("@@") || line.startsWith("---") || line.startsWith("+++")) {
                      className = "diff-header";
                    }
                    return (
                      <div key={idx} className={className}>
                        {line || " "}
                      </div>
                    );
                  })
                ) : (
                  <p style={{ color: "var(--text-muted)", fontStyle: "italic" }}>No diff recorded for this version.</p>
                )}
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button className="btn btn-secondary" onClick={() => setSelectedVersion(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
