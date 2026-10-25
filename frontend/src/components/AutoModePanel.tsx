import { useEffect, useState } from "react";
import type { FC } from "react";
import { Play, Pause, Square, Zap, Activity, Clock, ShieldCheck, ShieldAlert } from "lucide-react";
import type { AutoModeStatus, UserSession } from "../types";

interface AutoModePanelProps {
  user: UserSession;
}

export const AutoModePanel: FC<AutoModePanelProps> = ({ user }) => {
  const [status, setStatus] = useState<AutoModeStatus | null>(null);
  const [category, setCategory] = useState<string>("Living people");
  const [dryRun, setDryRun] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const [startError, setStartError] = useState<string | null>(null);

  const fetchStatus = async () => {
    try {
      const res = await fetch("/api/auto/status");
      if (res.ok) {
        const data: AutoModeStatus = await res.json();
        setStatus(data);
      }
    } catch (err) {
      console.error("Failed to fetch auto mode status", err);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 1000);
    return () => clearInterval(interval);
  }, []);

  const handleStart = async () => {
    setStartError(null);
    setLoading(true);
    try {
      const res = await fetch("/api/auto/start", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${user.token}`,
        },
        body: JSON.stringify({ category: category.trim(), dry_run: dryRun }),
      });
      if (!res.ok) {
        let errData: any = {};
        try {
          errData = await res.json();
        } catch {
          errData = {};
        }
        setStartError(errData.detail || errData.error || `Server error starting Auto Mode (${res.status})`);
      } else {
        setStartError(null);
      }
      fetchStatus();
    } catch (err: any) {
      setStartError(err.message || "Failed to connect to server.");
    } finally {
      setLoading(false);
    }
  };

  const handlePause = async () => {
    try {
      await fetch("/api/auto/pause", {
        method: "POST",
        headers: { Authorization: `Bearer ${user.token}` },
      });
      fetchStatus();
    } catch (err) {
      console.error(err);
    }
  };

  const handleResume = async () => {
    try {
      await fetch("/api/auto/resume", {
        method: "POST",
        headers: { Authorization: `Bearer ${user.token}` },
      });
      fetchStatus();
    } catch (err) {
      console.error(err);
    }
  };

  const handleStop = async () => {
    try {
      await fetch("/api/auto/stop", {
        method: "POST",
        headers: { Authorization: `Bearer ${user.token}` },
      });
      fetchStatus();
    } catch (err) {
      console.error(err);
    }
  };

  const isRunning = status?.state === "running";
  const isPaused = status?.state === "paused";
  const isStopped = !isRunning && !isPaused;

  return (
    <div>
      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Zap size={22} color="#38bdf8" />
            <h2 style={{ fontSize: "1.2rem", fontWeight: 700 }}>Automatic Continuous Archiving Mode</h2>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <span
              className={`badge ${
                isRunning
                  ? "badge-working"
                  : isPaused
                  ? "badge-inconclusive"
                  : "badge-unknown"
              }`}
              style={{ fontSize: "0.85rem", padding: "0.35rem 0.8rem", letterSpacing: "0.05em" }}
            >
              {status?.state.toUpperCase() || "STOPPED"}
            </span>
          </div>
        </div>

        <p style={{ fontSize: "0.875rem", color: "var(--text-muted)", marginBottom: "1.25rem" }}>
          Once enabled, Auto Mode automatically scans and repairs citations in batches, continuously preserving broken links and missing Wayback Machine snapshots under the identity of <strong>{user.username}</strong> without requiring manual intervention.
        </p>

        {/* Configuration Row */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "2fr 1fr",
            gap: "1rem",
            marginBottom: "1.25rem",
          }}
        >
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label">Target MediaWiki Category:</label>
            <input
              type="text"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              disabled={!isStopped}
              placeholder="e.g. Living people or Articles with dead external links"
            />
          </div>

          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label">Mode:</label>
            <select
              value={dryRun ? "dry_run" : "live_edit"}
              onChange={(e) => setDryRun(e.target.value === "dry_run")}
              disabled={!isStopped}
            >
              <option value="live_edit">Live Edit (Commit to Wiki)</option>
              <option value="dry_run">Dry-Run (Simulate & Save Versions)</option>
            </select>
          </div>
        </div>

        {startError && (
          <div
            style={{
              padding: "0.75rem 1rem",
              background: "rgba(239, 68, 68, 0.12)",
              border: "1px solid rgba(239, 68, 68, 0.3)",
              borderRadius: "8px",
              marginBottom: "1.25rem",
              fontSize: "0.85rem",
              color: "#f87171",
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
            }}
          >
            <ShieldAlert size={18} />
            <span>{startError}</span>
          </div>
        )}

        <div
          style={{
            padding: "0.75rem 1rem",
            background: "rgba(56, 189, 248, 0.08)",
            border: "1px solid rgba(56, 189, 248, 0.25)",
            borderRadius: "8px",
            marginBottom: "1.25rem",
            fontSize: "0.85rem",
            color: "#93c5fd",
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
          }}
        >
          <ShieldCheck size={18} color="#38bdf8" />
          <span>
            <strong>Active Operator:</strong> All citation enhancements will be attributed to <strong>{user.username}</strong> on Justapedia.
          </span>
        </div>

        {/* Controls Bar */}
        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", marginBottom: "1.5rem" }}>
          {isStopped && (
            <button
              className="btn btn-primary"
              onClick={handleStart}
              disabled={loading}
              style={{ padding: "0.75rem 1.75rem", fontSize: "1rem" }}
            >
              <Play size={18} /> Start Auto Mode
            </button>
          )}

          {isRunning && (
            <button
              className="btn btn-secondary"
              onClick={handlePause}
              style={{ padding: "0.75rem 1.5rem", fontSize: "1rem", background: "#f59e0b", color: "#000" }}
            >
              <Pause size={18} /> Pause Auto Mode
            </button>
          )}

          {isPaused && (
            <button
              className="btn btn-success"
              onClick={handleResume}
              style={{ padding: "0.75rem 1.5rem", fontSize: "1rem" }}
            >
              <Play size={18} /> Resume Auto Mode
            </button>
          )}

          {!isStopped && (
            <button
              className="btn btn-danger"
              onClick={handleStop}
              style={{ padding: "0.75rem 1.5rem", fontSize: "1rem" }}
            >
              <Square size={18} /> Stop
            </button>
          )}
        </div>

        {/* Real-time Telemetry Grid */}
        <div className="metrics-grid">
          <div className="metric-box">
            <div className="label">Throughput Speed</div>
            <div
              className="value"
              style={{
                color: (status?.speed_articles_per_minute || 0) >= 20 ? "#34d399" : "#38bdf8",
              }}
            >
              {status?.speed_articles_per_minute || 0}
              <span style={{ fontSize: "0.85rem", fontWeight: 500, color: "var(--text-muted)", marginLeft: "4px" }}>
                art/min
              </span>
            </div>
            {(status?.speed_articles_per_minute || 0) >= 20 && (
              <div style={{ fontSize: "0.7rem", color: "#34d399", fontWeight: 600, marginTop: "2px" }}>
                High-Speed (&gt; 20/min target achieved)
              </div>
            )}
          </div>

          <div className="metric-box">
            <div className="label">Articles Scanned</div>
            <div className="value">{status?.articles_scanned || 0}</div>
          </div>

          <div className="metric-box">
            <div className="label">Articles Updated</div>
            <div className="value" style={{ color: "#34d399" }}>
              {status?.articles_updated || 0}
            </div>
          </div>

          <div className="metric-box">
            <div className="label">Citations Saved</div>
            <div className="value" style={{ color: "#c084fc" }}>
              {status?.citations_updated || 0}
            </div>
          </div>
        </div>

        {/* Currently Processing Status */}
        {!isStopped && (
          <div
            style={{
              padding: "0.85rem 1rem",
              background: "#090d16",
              border: "1px solid var(--border-color)",
              borderRadius: "8px",
              marginBottom: "1.5rem",
              display: "flex",
              alignItems: "center",
              gap: "0.6rem",
            }}
          >
            <Activity size={18} color="#38bdf8" className="animate-spin" />
            <span style={{ fontSize: "0.875rem", color: "var(--text-muted)" }}>Currently Processing:</span>
            <strong style={{ fontSize: "0.95rem", color: "#f8fafc" }}>
              {status?.current_article || "Processing..."}
            </strong>
          </div>
        )}

        {/* Real-time Activity Feed */}
        <div>
          <h3 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <Clock size={16} color="#38bdf8" /> Live Processing Log
          </h3>
          <div
            style={{
              background: "#090d16",
              border: "1px solid var(--border-color)",
              borderRadius: "8px",
              padding: "0.75rem",
              maxHeight: "260px",
              overflowY: "auto",
              fontFamily: "ui-monospace, monospace",
              fontSize: "0.825rem",
            }}
          >
            {status?.recent_activities && status.recent_activities.length > 0 ? (
              status.recent_activities.map((act, idx) => (
                <div
                  key={idx}
                  style={{
                    padding: "0.35rem 0",
                    borderBottom: "1px solid rgba(255, 255, 255, 0.05)",
                    display: "flex",
                    gap: "0.6rem",
                    color:
                      act.level === "success"
                        ? "#34d399"
                        : act.level === "warning"
                        ? "#fbbf24"
                        : act.level === "error"
                        ? "#f87171"
                        : "#94a3b8",
                  }}
                >
                  <span style={{ color: "var(--text-muted)" }}>[{act.timestamp}]</span>
                  <span>{act.message}</span>
                </div>
              ))
            ) : (
              <p style={{ color: "var(--text-muted)", margin: 0 }}>
                No events recorded yet. Click "Start Auto Mode" to begin.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
