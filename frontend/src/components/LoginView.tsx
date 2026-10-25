import { useState } from "react";
import type { FC, FormEvent } from "react";
import { Archive, Lock, User, Key, AlertCircle, Loader2 } from "lucide-react";
import type { UserSession } from "../types";

interface LoginViewProps {
  onLoginSuccess: (session: UserSession) => void;
}

export const LoginView: FC<LoginViewProps> = ({ onLoginSuccess }) => {
  const [username, setUsername] = useState<string>("");
  const [password, setPassword] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const cleanUser = username.trim();
    const cleanPass = password.trim();

    if (!cleanUser || !cleanPass) {
      setError("Please enter your username and password.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: cleanUser,
          password: cleanPass,
        }),
      });

      let data: any = {};
      try {
        data = await res.json();
      } catch {
        data = {};
      }
      if (!res.ok) {
        throw new Error(data.detail || data.error || `Authentication failed (Status ${res.status}).`);
      }

      const session: UserSession = {
        token: data.token,
        username: data.username,
        user_id: data.user_id,
      };

      localStorage.setItem("justapedia_token", data.token);
      localStorage.setItem("justapedia_user", JSON.stringify(session));
      onLoginSuccess(session);
    } catch (err: any) {
      setError(err.message || "Unable to sign in. Please verify your username and password.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "82vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "1.5rem",
      }}
    >
      <div
        className="card"
        style={{
          width: "100%",
          maxWidth: "440px",
          background: "linear-gradient(180deg, #1e293b 0%, #0f172a 100%)",
          border: "1px solid rgba(56, 189, 248, 0.2)",
          boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.6), 0 0 25px rgba(56, 189, 248, 0.05)",
          borderRadius: "20px",
          padding: "2.75rem 2.25rem 2.25rem",
        }}
      >
        {/* Brand Header */}
        <div style={{ textAlign: "center", marginBottom: "2rem" }}>
          <div
            style={{
              width: "60px",
              height: "60px",
              borderRadius: "16px",
              background: "linear-gradient(135deg, rgba(56, 189, 248, 0.2) 0%, rgba(99, 102, 241, 0.2) 100%)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              margin: "0 auto 1.25rem",
              border: "1px solid rgba(56, 189, 248, 0.35)",
              boxShadow: "0 8px 16px -4px rgba(56, 189, 248, 0.2)",
            }}
          >
            <Archive size={30} color="#38bdf8" />
          </div>
          <h1
            style={{
              fontSize: "1.6rem",
              fontWeight: 700,
              letterSpacing: "-0.03em",
              marginBottom: "0.4rem",
              background: "linear-gradient(135deg, #ffffff 0%, #94a3b8 100%)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            Justapedia Archiver
          </h1>
          <p style={{ color: "#94a3b8", fontSize: "0.85rem", margin: 0, lineHeight: "1.4" }}>
            Sign in to access citation archiver tools and manage wiki citations.
          </p>
        </div>

        {/* Error Alert */}
        {error && (
          <div
            style={{
              padding: "0.85rem 1rem",
              background: "rgba(239, 68, 68, 0.1)",
              border: "1px solid rgba(239, 68, 68, 0.3)",
              borderRadius: "10px",
              marginBottom: "1.5rem",
              color: "#f87171",
              fontSize: "0.85rem",
              display: "flex",
              alignItems: "center",
              gap: "0.6rem",
            }}
          >
            <AlertCircle size={18} style={{ flexShrink: 0 }} />
            <span>{error}</span>
          </div>
        )}

        {/* Professional Form */}
        <form onSubmit={handleSubmit}>
          <div className="form-group" style={{ marginBottom: "1.25rem" }}>
            <label
              className="form-label"
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.4rem",
                color: "#e2e8f0",
                fontSize: "0.85rem",
                fontWeight: 600,
                marginBottom: "0.4rem",
              }}
            >
              <User size={15} color="#38bdf8" /> Username
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Enter your username"
              autoFocus
              required
              style={{
                width: "100%",
                padding: "0.75rem 1rem",
                background: "#090d16",
                border: "1px solid var(--border-color)",
                borderRadius: "10px",
                color: "#f8fafc",
                fontSize: "0.92rem",
                outline: "none",
                transition: "border-color 0.2s, box-shadow 0.2s",
              }}
            />
          </div>

          <div className="form-group" style={{ marginBottom: "1.75rem" }}>
            <label
              className="form-label"
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.4rem",
                color: "#e2e8f0",
                fontSize: "0.85rem",
                fontWeight: 600,
                marginBottom: "0.4rem",
              }}
            >
              <Key size={15} color="#38bdf8" /> Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter your password"
              required
              style={{
                width: "100%",
                padding: "0.75rem 1rem",
                background: "#090d16",
                border: "1px solid var(--border-color)",
                borderRadius: "10px",
                color: "#f8fafc",
                fontSize: "0.92rem",
                outline: "none",
                transition: "border-color 0.2s, box-shadow 0.2s",
              }}
            />
          </div>

          <button
            type="submit"
            className="btn btn-primary"
            disabled={loading || !username.trim() || !password.trim()}
            style={{
              width: "100%",
              padding: "0.85rem",
              fontSize: "0.95rem",
              fontWeight: 600,
              borderRadius: "10px",
              background: "linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%)",
              border: "1px solid rgba(59, 130, 246, 0.4)",
              boxShadow: "0 4px 12px rgba(37, 99, 235, 0.35)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "0.5rem",
              cursor: loading ? "wait" : "pointer",
            }}
          >
            {loading ? (
              <>
                <Loader2 size={18} className="animate-spin" /> Signing in...
              </>
            ) : (
              <>
                <Lock size={16} /> Sign In
              </>
            )}
          </button>
        </form>

        {/* Clean Footer Credit */}
        <div
          style={{
            marginTop: "2rem",
            paddingTop: "1.25rem",
            borderTop: "1px solid rgba(148, 163, 184, 0.12)",
            textAlign: "center",
            fontSize: "0.76rem",
            color: "#64748b",
          }}
        >
          Developer: <span style={{ color: "#94a3b8", fontWeight: 500 }}>Sourav Halder</span> &bull;{" "}
          <span style={{ color: "#38bdf8" }}>skhsouravhalder@gmail.com</span>
        </div>
      </div>
    </div>
  );
};
