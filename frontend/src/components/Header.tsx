import type { FC } from "react";
import { Archive, CheckCircle, AlertTriangle, User, LogOut } from "lucide-react";
import type { SystemStatus, UserSession } from "../types";

interface HeaderProps {
  status: SystemStatus | null;
  user: UserSession;
  onLogout: () => void;
}

export const Header: FC<HeaderProps> = ({ status, user, onLogout }) => {
  return (
    <header>
      <div className="brand">
        <Archive size={28} color="#38bdf8" />
        <div>
          <h1>Justapedia Wayback Bot Tools</h1>
          <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
            High-Speed Citation Archiving &amp; Broken Link Repair
          </p>
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
        {status ? (
          <span
            className={`status-pill ${
              status.wiki_connected ? "status-online" : "status-offline"
            }`}
          >
            {status.wiki_connected ? (
              <>
                <CheckCircle size={14} /> Wiki API Connected
              </>
            ) : (
              <>
                <AlertTriangle size={14} /> Wiki Disconnected
              </>
            )}
          </span>
        ) : (
          <span className="status-pill status-offline">Connecting...</span>
        )}

        {/* User Identity Pill (Requirement 4) */}
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.4rem",
            background: "rgba(56, 189, 248, 0.12)",
            border: "1px solid rgba(56, 189, 248, 0.3)",
            padding: "0.35rem 0.8rem",
            borderRadius: "9999px",
            fontSize: "0.85rem",
            fontWeight: 600,
            color: "#38bdf8",
          }}
        >
          <User size={15} />
          <span>{user.username}</span>
          {user.user_id && (
            <span style={{ fontSize: "0.75rem", opacity: 0.8, color: "var(--text-muted)" }}>
              (ID: {user.user_id})
            </span>
          )}
        </div>

        {/* Logout Button */}
        <button
          className="btn btn-secondary"
          onClick={onLogout}
          style={{ padding: "0.35rem 0.75rem", fontSize: "0.85rem" }}
          title="Log out"
        >
          <LogOut size={15} /> Log Out
        </button>
      </div>
    </header>
  );
};
