import { useState } from "react";
import type { FC } from "react";
import { ExternalLink, Filter } from "lucide-react";
import type { CitationItem } from "../types";

interface CitationsTableProps {
  citations: CitationItem[];
}

export const CitationsTable: FC<CitationsTableProps> = ({ citations }) => {
  const [filter, setFilter] = useState<string>("all");

  const filtered = citations.filter((c) => {
    if (filter === "all") return true;
    return c.url_health === filter;
  });

  if (citations.length === 0) {
    return null;
  }

  return (
    <div className="card">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "1rem",
        }}
      >
        <h2 style={{ fontSize: "1.1rem", fontWeight: 600 }}>
          Examined Citations ({filtered.length} of {citations.length})
        </h2>

        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <Filter size={16} color="var(--text-muted)" />
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{ width: "auto", padding: "0.35rem 0.75rem", fontSize: "0.85rem" }}
          >
            <option value="all">All Health Statuses</option>
            <option value="likely_dead">Likely Dead (404/410)</option>
            <option value="working">Working (200 OK)</option>
            <option value="inconclusive">Inconclusive (403/429/5xx)</option>
          </select>
        </div>
      </div>

      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Article</th>
              <th>Citation Title</th>
              <th>Original URL</th>
              <th>Health</th>
              <th>Archive URL & Date</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((item, idx) => (
              <tr key={idx}>
                <td style={{ fontWeight: 600 }}>{item.article_title}</td>
                <td style={{ maxWidth: "220px", wordBreak: "break-word" }}>
                  {item.citation_title || "(No Title)"}
                </td>
                <td style={{ maxWidth: "220px", wordBreak: "break-all" }}>
                  {item.original_url ? (
                    <a
                      href={item.original_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: "#38bdf8", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: "3px" }}
                    >
                      {item.original_url.length > 40
                        ? item.original_url.substring(0, 40) + "..."
                        : item.original_url}
                      <ExternalLink size={12} />
                    </a>
                  ) : (
                    "—"
                  )}
                </td>
                <td>
                  <span className={`badge badge-${item.url_health}`}>
                    {item.url_health}
                  </span>
                </td>
                <td style={{ maxWidth: "220px", wordBreak: "break-all" }}>
                  {item.archive_url ? (
                    <div>
                      <a
                        href={item.archive_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ color: "#34d399", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: "3px" }}
                      >
                        {item.archive_date || "Snapshot"}
                        <ExternalLink size={12} />
                      </a>
                    </div>
                  ) : (
                    <span style={{ color: "var(--text-muted)" }}>None found</span>
                  )}
                </td>
                <td>
                  <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                    {item.reason}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
