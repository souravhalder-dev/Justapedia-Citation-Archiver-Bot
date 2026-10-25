import { useState } from "react";
import type { FC } from "react";
import { Play, Search, AlertCircle, ShieldAlert, Loader2 } from "lucide-react";
import type { ScanResponse, UserSession } from "../types";
import { DiffViewer } from "./DiffViewer";
import { CitationsTable } from "./CitationsTable";

interface ArticleScannerProps {
  user: UserSession;
}

export const ArticleScanner: FC<ArticleScannerProps> = ({ user }) => {
  const [targetType, setTargetType] = useState<"article" | "category" | "titles">("article");
  const [target, setTarget] = useState<string>("Kevin Gorey");
  const [mode, setMode] = useState<"dry_run" | "live_edit">("dry_run");
  const [maxEdits, setMaxEdits] = useState<number>(5);
  const [limit, setLimit] = useState<number>(20);
  const [loading, setLoading] = useState<boolean>(false);
  const [response, setResponse] = useState<ScanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleScan = async () => {
    if (!target.trim()) {
      setError("Please provide an article title, category, or title list.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await fetch("/api/scan", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${user.token}`,
        },
        body: JSON.stringify({
          target_type: targetType,
          target: target.trim(),
          mode,
          max_edits: maxEdits,
          limit,
        }),
      });

      let data: any = {};
      try {
        data = await res.json();
      } catch {
        data = {};
      }

      if (!res.ok) {
        throw new Error(data.detail || data.error || `Server returned HTTP ${res.status}`);
      }

      if (data.error) {
        setError(data.error);
      } else {
        setResponse(data);
      }
    } catch (err: any) {
      setError(err.message || "An error occurred during scanning.");
    } finally {
      setLoading(false);
    }
  };

  const m = response?.report?.metrics;

  return (
    <div>
      <div className="card">
        <h2 className="card-title">
          <Search size={20} color="#38bdf8" /> Configure Archiving Scan
        </h2>

        {/* Target Type Selector */}
        <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem" }}>
          <button
            type="button"
            className={`tab-btn ${targetType === "article" ? "active" : ""}`}
            onClick={() => {
              setTargetType("article");
              setTarget("Kevin Gorey");
            }}
          >
            Single Article
          </button>
          <button
            type="button"
            className={`tab-btn ${targetType === "category" ? "active" : ""}`}
            onClick={() => {
              setTargetType("category");
              setTarget("Living people");
            }}
          >
            Category
          </button>
          <button
            type="button"
            className={`tab-btn ${targetType === "titles" ? "active" : ""}`}
            onClick={() => {
              setTargetType("titles");
              setTarget("Kevin Gorey\nAustin Robertson\nSeething Wells");
            }}
          >
            Batch Title List
          </button>
        </div>

        {/* Input Field */}
        <div className="form-group">
          <label className="form-label">
            {targetType === "article" && "Article Title:"}
            {targetType === "category" && "Category Name (e.g. 'Living people'):"}
            {targetType === "titles" && "Article Titles (one per line):"}
          </label>
          {targetType === "titles" ? (
            <textarea
              rows={4}
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              placeholder="Paste article titles here..."
            />
          ) : (
            <input
              type="text"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              placeholder={
                targetType === "article" ? "e.g. Kevin Gorey" : "e.g. Living people"
              }
            />
          )}
        </div>

        {/* Options Row */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
            gap: "1rem",
            marginBottom: "1.25rem",
          }}
        >
          <div>
            <label className="form-label">Execution Mode:</label>
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value as "dry_run" | "live_edit")}
            >
              <option value="dry_run">Dry-Run (Simulate & Preview Diffs)</option>
              <option value="live_edit">
                Live Edit (Apply directly under {user.username})
              </option>
            </select>
          </div>

          {targetType !== "article" && (
            <div>
              <label className="form-label">Article Limit:</label>
              <input
                type="number"
                min={1}
                max={200}
                value={limit}
                onChange={(e) => setLimit(parseInt(e.target.value) || 20)}
              />
            </div>
          )}

          {mode === "live_edit" && (
            <div>
              <label className="form-label">Max Edits Cap:</label>
              <input
                type="number"
                min={1}
                max={50}
                value={maxEdits}
                onChange={(e) => setMaxEdits(parseInt(e.target.value) || 5)}
              />
            </div>
          )}
        </div>

        {mode === "live_edit" && (
          <div
            style={{
              padding: "0.75rem 1rem",
              background: "rgba(239, 68, 68, 0.15)",
              border: "1px solid rgba(239, 68, 68, 0.3)",
              borderRadius: "8px",
              marginBottom: "1.25rem",
              fontSize: "0.85rem",
              color: "#fca5a5",
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
            }}
          >
            <ShieldAlert size={18} />
            <strong>Caution:</strong> Live edit mode will commit actual revisions to Justapedia directly under your account: <strong>{user.username}</strong>.
          </div>
        )}

        {error && (
          <div
            style={{
              padding: "0.75rem 1rem",
              background: "rgba(239, 68, 68, 0.1)",
              border: "1px solid rgba(239, 68, 68, 0.3)",
              borderRadius: "8px",
              marginBottom: "1rem",
              color: "#f87171",
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              fontSize: "0.85rem",
            }}
          >
            <AlertCircle size={16} />
            {error}
          </div>
        )}

        <button
          className="btn btn-primary"
          onClick={handleScan}
          disabled={loading}
          style={{ width: "100%", padding: "0.8rem", fontSize: "1rem" }}
        >
          {loading ? (
            <>
              <Loader2 size={18} className="animate-spin" /> High-Speed Batch Scanning...
            </>
          ) : (
            <>
              <Play size={18} /> Run Archiving Scan
            </>
          )}
        </button>
      </div>

      {/* Metrics Summary */}
      {m && (
        <div className="metrics-grid">
          <div className="metric-box">
            <div className="label">Articles Scanned</div>
            <div className="value">{m.articles_scanned}</div>
          </div>
          <div className="metric-box">
            <div className="label">Citations Examined</div>
            <div className="value">{m.citations_examined}</div>
          </div>
          <div className="metric-box">
            <div className="label">Working URLs</div>
            <div className="value" style={{ color: "#34d399" }}>
              {m.working_urls}
            </div>
          </div>
          <div className="metric-box">
            <div className="label">Likely Dead URLs</div>
            <div className="value" style={{ color: "#f87171" }}>
              {m.potentially_dead_urls}
            </div>
          </div>
          <div className="metric-box">
            <div className="label">Archives Found</div>
            <div className="value" style={{ color: "#38bdf8" }}>
              {m.archives_found}
            </div>
          </div>
          <div className="metric-box">
            <div className="label">Params Added</div>
            <div className="value" style={{ color: "#c084fc" }}>
              {m.archive_params_added}
            </div>
          </div>
        </div>
      )}

      {/* Diffs & Citations Table */}
      {response && response.diffs && (
        <DiffViewer diffs={response.diffs} canApply={true} />
      )}

      {response && response.report && response.report.citations && (
        <CitationsTable citations={response.report.citations} />
      )}
    </div>
  );
};
