import { useEffect, useState } from "react";
import type { FC } from "react";
import { History } from "lucide-react";
import type { JobRecord, UserSession } from "../types";

interface JobHistoryProps {
  user: UserSession;
}

export const JobHistory: FC<JobHistoryProps> = ({ user }) => {
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [jobArticles, setJobArticles] = useState<any[]>([]);

  const fetchJobs = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/jobs?limit=20", {
        headers: { Authorization: `Bearer ${user.token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setJobs(data);
      }
    } catch (err) {
      console.error("Failed to load jobs", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchJobs();
  }, []);

  const handleSelectJob = async (jobId: string) => {
    setSelectedJobId(jobId);
    try {
      const res = await fetch(`/api/jobs/${jobId}`, {
        headers: { Authorization: `Bearer ${user.token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setJobArticles(data.articles || []);
      }
    } catch (err) {
      console.error("Failed to load job articles", err);
    }
  };

  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
        <h2 className="card-title" style={{ marginBottom: 0 }}>
          <History size={20} color="#38bdf8" /> Past Scanning & Archiving Jobs
        </h2>
        <button className="btn btn-secondary" onClick={fetchJobs} style={{ padding: "0.4rem 0.8rem", fontSize: "0.85rem" }}>
          Refresh
        </button>
      </div>

      {loading ? (
        <p style={{ color: "var(--text-muted)", fontSize: "0.9rem" }}>Loading job history...</p>
      ) : jobs.length === 0 ? (
        <p style={{ color: "var(--text-muted)", fontSize: "0.9rem" }}>No past jobs found in database.</p>
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Job ID</th>
                <th>Target</th>
                <th>Mode</th>
                <th>Status</th>
                <th>Articles</th>
                <th>Citations</th>
                <th>Archives Added</th>
                <th>Time</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id} style={{ background: selectedJobId === j.id ? "rgba(56, 189, 248, 0.08)" : undefined }}>
                  <td style={{ fontFamily: "monospace", fontSize: "0.85rem" }}>{j.id}</td>
                  <td style={{ fontWeight: 600 }}>{j.target} ({j.target_type})</td>
                  <td>
                    <span className={`badge ${j.mode === "live_edit" ? "badge-likely_dead" : "badge-working"}`}>
                      {j.mode}
                    </span>
                  </td>
                  <td>
                    <span className="badge badge-working">{j.status}</span>
                  </td>
                  <td>{j.articles_scanned}</td>
                  <td>{j.citations_examined}</td>
                  <td>{j.archives_added}</td>
                  <td style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                    {new Date(j.created_at).toLocaleString()}
                  </td>
                  <td>
                    <button
                      className="btn btn-secondary"
                      onClick={() => handleSelectJob(j.id)}
                      style={{ padding: "0.25rem 0.6rem", fontSize: "0.8rem" }}
                    >
                      Articles
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selectedJobId && jobArticles.length > 0 && (
        <div style={{ marginTop: "1.5rem" }}>
          <h3 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "0.75rem" }}>
            Articles in Job #{selectedJobId}
          </h3>
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Article Title</th>
                  <th>Status</th>
                  <th>Citations</th>
                  <th>Updated</th>
                  <th>Summary</th>
                </tr>
              </thead>
              <tbody>
                {jobArticles.map((a, idx) => (
                  <tr key={idx}>
                    <td style={{ fontWeight: 600 }}>{a.title}</td>
                    <td><span className="badge badge-working">{a.status}</span></td>
                    <td>{a.citations_examined}</td>
                    <td>{a.citations_updated}</td>
                    <td style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>{a.summary}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
