import { useState } from "react";
import type { FC } from "react";
import { GitCompare, Copy, Check, Send, CheckCircle2, AlertCircle } from "lucide-react";

interface DiffViewerProps {
  diffs: Record<string, string>;
  canApply?: boolean;
}

export const DiffViewer: FC<DiffViewerProps> = ({ diffs, canApply }) => {
  const titles = Object.keys(diffs);
  const [selectedTitle, setSelectedTitle] = useState<string>(
    titles.length > 0 ? titles[0] : ""
  );
  const [copied, setCopied] = useState<boolean>(false);
  const [applying, setApplying] = useState<boolean>(false);
  const [applyResult, setApplyResult] = useState<{ success: boolean; msg: string } | null>(null);

  if (titles.length === 0) {
    return (
      <div className="card" style={{ textAlign: "center", color: "var(--text-muted)" }}>
        <GitCompare size={36} style={{ margin: "0 auto 0.75rem", opacity: 0.5 }} />
        <p>No Wikitext differences generated yet. Run a scan to inspect changes.</p>
      </div>
    );
  }

  const currentDiff = diffs[selectedTitle] || "";

  const handleCopy = () => {
    navigator.clipboard.writeText(currentDiff);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleApply = async () => {
    const token = localStorage.getItem("justapedia_token");
    if (!token) {
      alert("Please log in to apply changes.");
      return;
    }

    setApplying(true);
    setApplyResult(null);

    try {
      const res = await fetch("/api/apply", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          title: selectedTitle,
          wikitext: currentDiff, // backend handles revision fetching or diff application
          summary: `Bot: Added Wayback Machine archive information to citations`,
        }),
      });

      let data: any = {};
      try {
        data = await res.json();
      } catch {
        data = {};
      }
      if (res.ok && data.success) {
        setApplyResult({ success: true, msg: data.message || "Revision saved successfully!" });
      } else {
        setApplyResult({ success: false, msg: data.detail || data.message || `Failed to save revision (HTTP ${res.status})` });
      }
    } catch (err: any) {
      setApplyResult({ success: false, msg: err.message || "Network error" });
    } finally {
      setApplying(false);
    }
  };

  return (
    <div className="card">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "1rem",
          flexWrap: "wrap",
          gap: "0.5rem",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <GitCompare size={20} color="#38bdf8" />
          <h2 style={{ fontSize: "1.1rem", fontWeight: 600 }}>Proposed Wikitext Changes</h2>
        </div>

        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <button className="btn btn-secondary" onClick={handleCopy}>
            {copied ? <Check size={16} color="#34d399" /> : <Copy size={16} />}
            {copied ? "Copied" : "Copy Diff"}
          </button>

          {canApply && (
            <button
              className="btn btn-success"
              onClick={handleApply}
              disabled={applying}
            >
              <Send size={16} /> {applying ? "Applying..." : "Apply to Wiki"}
            </button>
          )}
        </div>
      </div>

      {applyResult && (
        <div
          style={{
            padding: "0.6rem 0.9rem",
            borderRadius: "6px",
            marginBottom: "1rem",
            fontSize: "0.85rem",
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            background: applyResult.success ? "rgba(52, 211, 153, 0.15)" : "rgba(248, 113, 113, 0.15)",
            color: applyResult.success ? "#34d399" : "#f87171",
            border: `1px solid ${applyResult.success ? "rgba(52, 211, 153, 0.3)" : "rgba(248, 113, 113, 0.3)"}`,
          }}
        >
          {applyResult.success ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
          <span>{applyResult.msg}</span>
        </div>
      )}

      {titles.length > 1 && (
        <div style={{ marginBottom: "1rem", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          {titles.map((t) => (
            <button
              key={t}
              onClick={() => setSelectedTitle(t)}
              className={`btn ${selectedTitle === t ? "btn-primary" : "btn-secondary"}`}
              style={{ fontSize: "0.85rem", padding: "0.35rem 0.75rem" }}
            >
              {t}
            </button>
          ))}
        </div>
      )}

      <div className="diff-container">
        {currentDiff.split("\n").map((line, idx) => {
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
        })}
      </div>
    </div>
  );
};
