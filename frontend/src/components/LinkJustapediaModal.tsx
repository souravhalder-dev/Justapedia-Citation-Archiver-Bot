import React, { useState } from "react";
import { KeyRound, Cookie, ExternalLink, CheckCircle2, AlertCircle, X, ShieldCheck } from "lucide-react";
import type { UserSession } from "../types";

interface LinkJustapediaModalProps {
  user: UserSession;
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export const LinkJustapediaModal: React.FC<LinkJustapediaModalProps> = ({
  user,
  isOpen,
  onClose,
  onSuccess,
}) => {
  const [activeTab, setActiveTab] = useState<"oauth" | "cookie">("oauth");

  // OAuth state
  const [oauthToken, setOauthToken] = useState<string>("");
  const [verifier, setVerifier] = useState<string>("");
  const [oauthInitiated, setOauthInitiated] = useState<boolean>(false);

  // Cookie state
  const [cookieInput, setCookieInput] = useState<string>("");

  // Status
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleInitiateOAuth = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/oauth/initiate", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${user.token}`,
        },
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to initiate Justapedia OAuth flow.");
      }
      setOauthToken(data.oauth_token);
      setOauthInitiated(true);
      window.open(data.authorize_url, "_blank");
    } catch (err: any) {
      setError(err.message || "Failed to start OAuth.");
    } finally {
      setLoading(false);
    }
  };

  const handleCompleteOAuth = async () => {
    if (!verifier.trim()) {
      setError("Please paste the verification PIN provided by Justapedia.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/link-oauth", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${user.token}`,
        },
        body: JSON.stringify({
          oauth_token: oauthToken,
          oauth_verifier: verifier.trim(),
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "OAuth verification failed.");
      }
      setSuccessMsg(data.message || "Justapedia account linked successfully via OAuth!");
      setTimeout(() => {
        onSuccess();
        onClose();
      }, 1500);
    } catch (err: any) {
      setError(err.message || "OAuth linking error.");
    } finally {
      setLoading(false);
    }
  };

  const handleSaveCookie = async () => {
    if (!cookieInput.trim()) {
      setError("Please paste your Justapedia session cookie (e.g. justapedia_session=...).");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/link-cookie", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${user.token}`,
        },
        body: JSON.stringify({ cookie: cookieInput.trim() }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Session cookie was rejected or expired.");
      }
      setSuccessMsg(data.message || "Justapedia session cookie connected successfully!");
      setTimeout(() => {
        onSuccess();
        onClose();
      }, 1500);
    } catch (err: any) {
      setError(err.message || "Failed to link session cookie.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: "rgba(10, 15, 29, 0.82)",
        backdropFilter: "blur(4px)",
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
          maxWidth: "540px",
          background: "var(--card-bg, #1e293b)",
          border: "1px solid var(--border-color, #334155)",
          boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.5)",
          padding: "1.75rem",
          position: "relative",
        }}
      >
        <button
          onClick={onClose}
          style={{
            position: "absolute",
            top: "1.25rem",
            right: "1.25rem",
            background: "transparent",
            border: "none",
            color: "var(--text-muted)",
            cursor: "pointer",
          }}
        >
          <X size={20} />
        </button>

        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "0.5rem" }}>
          <ShieldCheck size={24} color="#38bdf8" />
          <h2 style={{ fontSize: "1.25rem", fontWeight: 700, margin: 0 }}>Connect Justapedia Account</h2>
        </div>
        <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginBottom: "1.25rem" }}>
          Authenticating connects your Justapedia account ({user.username}) so live edits bypass firewall blocks (HTTP 429) and appear directly under your contributions.
        </p>

        {/* Tab buttons */}
        <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.25rem" }}>
          <button
            className={`btn ${activeTab === "oauth" ? "btn-primary" : "btn-secondary"}`}
            style={{ flex: 1, display: "flex", justifyContent: "center", gap: "0.4rem" }}
            onClick={() => {
              setActiveTab("oauth");
              setError(null);
            }}
          >
            <KeyRound size={16} /> Justapedia OAuth (1-Click)
          </button>
          <button
            className={`btn ${activeTab === "cookie" ? "btn-primary" : "btn-secondary"}`}
            style={{ flex: 1, display: "flex", justifyContent: "center", gap: "0.4rem" }}
            onClick={() => {
              setActiveTab("cookie");
              setError(null);
            }}
          >
            <Cookie size={16} /> Session Cookie
          </button>
        </div>

        {error && (
          <div
            style={{
              padding: "0.75rem 1rem",
              background: "rgba(239, 68, 68, 0.12)",
              border: "1px solid rgba(239, 68, 68, 0.3)",
              borderRadius: "8px",
              color: "#f87171",
              fontSize: "0.85rem",
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              marginBottom: "1rem",
            }}
          >
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}

        {successMsg && (
          <div
            style={{
              padding: "0.75rem 1rem",
              background: "rgba(34, 197, 94, 0.12)",
              border: "1px solid rgba(34, 197, 94, 0.3)",
              borderRadius: "8px",
              color: "#4ade80",
              fontSize: "0.85rem",
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              marginBottom: "1rem",
            }}
          >
            <CheckCircle2 size={16} />
            <span>{successMsg}</span>
          </div>
        )}

        {activeTab === "oauth" ? (
          <div>
            <div style={{ marginBottom: "1.25rem" }}>
              <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
                Step 1: Click the button below to authorize the bot on Justapedia.
              </p>
              <button
                className="btn btn-secondary"
                onClick={handleInitiateOAuth}
                disabled={loading}
                style={{ width: "100%", display: "flex", justifyContent: "center", gap: "0.5rem" }}
              >
                <ExternalLink size={16} /> Open Justapedia to Authorize
              </button>
            </div>

            {oauthInitiated && (
              <div style={{ marginBottom: "1.25rem" }}>
                <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginBottom: "0.5rem" }}>
                  Step 2: Paste the verification PIN displayed on Justapedia:
                </p>
                <input
                  type="text"
                  placeholder="e.g. 7a8b9c..."
                  value={verifier}
                  onChange={(e) => setVerifier(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "0.6rem 0.8rem",
                    borderRadius: "6px",
                    border: "1px solid var(--border-color, #334155)",
                    background: "rgba(15, 23, 42, 0.6)",
                    color: "white",
                    marginBottom: "0.75rem",
                  }}
                />
                <button
                  className="btn btn-primary"
                  onClick={handleCompleteOAuth}
                  disabled={loading}
                  style={{ width: "100%" }}
                >
                  {loading ? "Verifying..." : "Verify & Complete Connection"}
                </button>
              </div>
            )}
          </div>
        ) : (
          <div>
            <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
              Paste your browser's active Justapedia cookie string (from browser DevTools &gt; Application &gt; Cookies):
            </p>
            <textarea
              rows={4}
              placeholder="justapedia_session=xyz123...; justapedia_user=Sourav"
              value={cookieInput}
              onChange={(e) => setCookieInput(e.target.value)}
              style={{
                width: "100%",
                padding: "0.6rem 0.8rem",
                borderRadius: "6px",
                border: "1px solid var(--border-color, #334155)",
                background: "rgba(15, 23, 42, 0.6)",
                color: "white",
                fontSize: "0.85rem",
                marginBottom: "1rem",
                fontFamily: "monospace",
              }}
            />
            <button
              className="btn btn-primary"
              onClick={handleSaveCookie}
              disabled={loading}
              style={{ width: "100%" }}
            >
              {loading ? "Validating..." : "Connect Session Cookie"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
