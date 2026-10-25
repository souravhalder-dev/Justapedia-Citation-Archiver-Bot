import { useEffect, useState } from "react";
import type { FC } from "react";
import { Archive, CheckCircle, AlertTriangle, User, LogOut, ShieldCheck, Link2 } from "lucide-react";
import type { SystemStatus, UserSession } from "../types";
import { LinkJustapediaModal } from "./LinkJustapediaModal";

interface HeaderProps {
  status: SystemStatus | null;
  user: UserSession;
  onLogout: () => void;
}

export const Header: FC<HeaderProps> = ({ status, user, onLogout }) => {
  const [wikiStatus, setWikiStatus] = useState<{
    is_linked: boolean;
    username?: string;
    auth_type?: string;
  } | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const fetchWikiStatus = async () => {
    try {
      const res = await fetch("/api/auth/wiki-status", {
        headers: { Authorization: `Bearer ${user.token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setWikiStatus(data);
      }
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    fetchWikiStatus();
  }, []);

  return (
    <>
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

          {/* Justapedia Live Edit Authentication Badge */}
          {wikiStatus?.is_linked ? (
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.4rem",
                background: "rgba(34, 197, 94, 0.12)",
                border: "1px solid rgba(34, 197, 94, 0.3)",
                padding: "0.35rem 0.8rem",
                borderRadius: "9999px",
                fontSize: "0.82rem",
                fontWeight: 600,
                color: "#4ade80",
              }}
              title="Authenticated to Justapedia for live edits"
            >
              <ShieldCheck size={14} />
              <span>Justapedia: Connected ({wikiStatus.username || user.username})</span>
            </div>
          ) : (
            <button
              onClick={() => setIsModalOpen(true)}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.4rem",
                background: "rgba(245, 158, 11, 0.12)",
                border: "1px solid rgba(245, 158, 11, 0.4)",
                padding: "0.35rem 0.8rem",
                borderRadius: "9999px",
                fontSize: "0.82rem",
                fontWeight: 600,
                color: "#fbbf24",
                cursor: "pointer",
              }}
              title="Click to connect Justapedia account for live edits"
            >
              <Link2 size={14} />
              <span>Connect Justapedia Account</span>
            </button>
          )}

          {/* User Identity Pill */}
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

      <LinkJustapediaModal
        user={user}
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSuccess={fetchWikiStatus}
      />
    </>
  );
};
