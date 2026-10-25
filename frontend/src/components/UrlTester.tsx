import { useState } from "react";
import type { FC } from "react";
import { Link2, ExternalLink, RefreshCw, CheckCircle, AlertTriangle, XCircle, Clock } from "lucide-react";
import type { UrlCheckResult, UserSession } from "../types";

interface UrlTesterProps {
  user: UserSession;
}

export const UrlTester: FC<UrlTesterProps> = ({ user }) => {
  const [url, setUrl] = useState<string>("https://www.statnews.com/2017/03/13/cystic-fibrosis-canadians-americans/");
  const [targetDate, setTargetDate] = useState<string>("2017-03-13");
  const [bypassCache, setBypassCache] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const [result, setResult] = useState<UrlCheckResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleTest = async () => {
    if (!url.trim()) return;
    setLoading(true);
    setError(null);

    try {
      const res = await fetch("/api/check-url", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${user.token}`,
        },
        body: JSON.stringify({
          url: url.trim(),
          target_date: targetDate.trim() || undefined,
          bypass_cache: bypassCache,
        }),
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const data: UrlCheckResult = await res.json();
      setResult(data);
    } catch (err: any) {
      setError(err.message || "Failed to check URL");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card">
      <h2 className="card-title">
        <Link2 size={20} color="#38bdf8" /> URL Health & Wayback Snapshot Inspector
      </h2>
      <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginBottom: "1.25rem" }}>
        Test any single URL to see real-time HTTP health, Internet Archive Availability API response, and historical CDX captures.
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "1rem", marginBottom: "1rem" }}>
        <div className="form-group" style={{ marginBottom: 0 }}>
          <label className="form-label">URL to Inspect:</label>
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com/article"
          />
        </div>

        <div className="form-group" style={{ marginBottom: 0 }}>
          <label className="form-label">Target Date (Optional):</label>
          <input
            type="text"
            value={targetDate}
            onChange={(e) => setTargetDate(e.target.value)}
            placeholder="YYYY-MM-DD or Month D, YYYY"
          />
        </div>
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
        <label style={{ fontSize: "0.85rem", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: "0.4rem", cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={bypassCache}
            onChange={(e) => setBypassCache(e.target.checked)}
          />
          Bypass SQLite Cache (Force Fresh Check)
        </label>

        <button className="btn btn-primary" onClick={handleTest} disabled={loading}>
          {loading ? (
            <>
              <RefreshCw size={16} className="animate-spin" /> Checking...
            </>
          ) : (
            <>
              <Link2 size={16} /> Check URL & Archives
            </>
          )}
        </button>
      </div>

      {error && (
        <div style={{ padding: "0.75rem", background: "rgba(239, 68, 68, 0.15)", borderRadius: "8px", color: "#f87171", fontSize: "0.85rem", marginBottom: "1rem" }}>
          {error}
        </div>
      )}

      {result && (
        <div style={{ marginTop: "1.5rem" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1.5rem" }}>
            {/* Health Box */}
            <div style={{ background: "#090d16", padding: "1rem", borderRadius: "8px", border: "1px solid var(--border-color)" }}>
              <h3 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                {result.health.status === "working" ? (
                  <CheckCircle size={18} color="#34d399" />
                ) : result.health.status === "likely_dead" ? (
                  <XCircle size={18} color="#f87171" />
                ) : (
                  <AlertTriangle size={18} color="#fbbf24" />
                )}
                HTTP Health Status
              </h3>
              <p style={{ fontSize: "0.85rem", marginBottom: "0.3rem" }}>
                Classification: <span className={`badge badge-${result.health.status}`}>{result.health.status}</span>
              </p>
              <p style={{ fontSize: "0.85rem", marginBottom: "0.3rem" }}>
                HTTP Code: <strong>{result.health.http_code || "N/A"}</strong>
              </p>
              {result.health.final_url && (
                <p style={{ fontSize: "0.85rem", marginBottom: "0.3rem", wordBreak: "break-all" }}>
                  Final URL: <span style={{ color: "var(--text-muted)" }}>{result.health.final_url}</span>
                </p>
              )}
              {result.health.is_cached && (
                <p style={{ fontSize: "0.75rem", color: "#94a3b8" }}>Served from SQLite Cache</p>
              )}
            </div>

            {/* Archive Box */}
            <div style={{ background: "#090d16", padding: "1rem", borderRadius: "8px", border: "1px solid var(--border-color)" }}>
              <h3 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <Clock size={18} color="#38bdf8" /> Wayback Machine Snapshot
              </h3>
              {result.snapshot ? (
                <>
                  <p style={{ fontSize: "0.85rem", marginBottom: "0.3rem" }}>
                    Selected Archive Date: <strong>{result.snapshot.formatted_date}</strong>
                  </p>
                  <p style={{ fontSize: "0.85rem", marginBottom: "0.5rem", wordBreak: "break-all" }}>
                    <a
                      href={result.snapshot.archive_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: "#34d399", display: "inline-flex", alignItems: "center", gap: "4px" }}
                    >
                      Open Snapshot on Wayback <ExternalLink size={12} />
                    </a>
                  </p>
                  <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                    Source: {result.snapshot.source_api.toUpperCase()} (Status: {result.snapshot.status_code})
                  </p>
                </>
              ) : (
                <p style={{ fontSize: "0.85rem", color: "#f87171" }}>
                  No available snapshot found for this URL.
                </p>
              )}
            </div>
          </div>

          {/* CDX Table */}
          {result.recent_cdx_captures && result.recent_cdx_captures.length > 0 && (
            <div>
              <h4 style={{ fontSize: "0.9rem", fontWeight: 600, marginBottom: "0.5rem" }}>
                Recent CDX Captures ({result.recent_cdx_captures.length})
              </h4>
              <div className="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Timestamp</th>
                      <th>HTTP Code</th>
                      <th>MIME Type</th>
                      <th>Direct Link</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.recent_cdx_captures.map((c, idx) => (
                      <tr key={idx}>
                        <td>{c.date}</td>
                        <td>{c.timestamp}</td>
                        <td><span className="badge badge-working">{c.status_code}</span></td>
                        <td>{c.mime_type}</td>
                        <td>
                          <a
                            href={c.archive_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ color: "#38bdf8", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: "3px" }}
                          >
                            View Capture <ExternalLink size={12} />
                          </a>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
