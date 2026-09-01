"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import api, { API_BASE } from "@/lib/api";
import { Application, STATUS_LABELS } from "@/lib/types";
import { FileCheck2, Trash2, ExternalLink, Mail, MessageSquare, Gift, XCircle, Clock } from "lucide-react";
import toast from "react-hot-toast";

const STATUS_ICONS: Record<string, React.ReactNode> = {
  pending: <Clock size={14} />,
  interview: <MessageSquare size={14} />,
  offer: <Gift size={14} />,
  rejected: <XCircle size={14} />,
};

const STATUS_COLORS: Record<string, string> = {
  pending: "var(--text2)",
  interview: "var(--accent2)",
  offer: "var(--green)",
  rejected: "var(--red)",
};

export default function ApplicationsPage() {
  const qc = useQueryClient();

  const { data: apps = [], isLoading } = useQuery<Application[]>({
    queryKey: ["applications"],
    queryFn: () => api.get("/applications/"),
  });

  const updateStatusMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) => 
      api.patch(`/applications/${id}/status`, { response_status: status }),
    onSuccess: () => {
      toast.success("Status updated");
      qc.invalidateQueries({ queryKey: ["applications"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.delete(`/applications/${id}`),
    onSuccess: () => {
      toast.success("Application removed");
      qc.invalidateQueries({ queryKey: ["applications"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
  });

  if (isLoading) return <div className="spinner" />;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Applications</h1>
        <p className="page-subtitle">Track and manage your job applications pipeline</p>
      </div>

      {apps.length === 0 ? (
        <div className="empty">
          <FileCheck2 size={48} style={{ margin: "0 auto 16px", color: "var(--text3)", opacity: 0.5 }} />
          <h3>No applications yet</h3>
          <p>Go to the Jobs board to start generating and sending applications.</p>
          <Link href="/jobs" className="btn btn-primary" style={{ marginTop: 16 }}>
            Browse Jobs
          </Link>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {apps.map((app) => (
            <div key={app.id} className="card" style={{ display: "flex", gap: 20, alignItems: "center", padding: "16px 24px" }}>
              
              {/* Left Info */}
              <div style={{ flex: 1 }}>
                <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>
                  <Link href={`/jobs/${app.job_id}`} className="hover:underline" style={{ color: "inherit", textDecoration: "none" }}>
                    {app.job_title}
                  </Link>
                </h3>
                <div style={{ display: "flex", gap: 12, alignItems: "center", fontSize: 14, color: "var(--text2)" }}>
                  <span style={{ fontWeight: 600, color: "var(--text)" }}>{app.company}</span>
                  {app.email_sent ? (
                    <span style={{ display: "flex", alignItems: "center", gap: 4, color: "var(--green)", fontSize: 13 }}>
                      <Mail size={13} /> Sent
                    </span>
                  ) : (
                    <span style={{ display: "flex", alignItems: "center", gap: 4, color: "var(--yellow)", fontSize: 13 }}>
                      <Mail size={13} /> Draft
                    </span>
                  )}
                </div>
              </div>

              {/* Status Dropdown */}
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <div style={{ 
                  display: "flex", alignItems: "center", gap: 6, 
                  padding: "6px 12px", borderRadius: "20px",
                  background: `color-mix(in srgb, ${STATUS_COLORS[app.response_status] || "var(--text2)"} 15%, transparent)`,
                  color: STATUS_COLORS[app.response_status] || "var(--text2)",
                  border: `1px solid color-mix(in srgb, ${STATUS_COLORS[app.response_status] || "var(--text2)"} 30%, transparent)`,
                  fontSize: 13, fontWeight: 600
                }}>
                  {STATUS_ICONS[app.response_status]}
                  <select 
                    value={app.response_status}
                    onChange={(e) => updateStatusMutation.mutate({ id: app.id, status: e.target.value })}
                    style={{ 
                      background: "transparent", border: "none", color: "inherit", 
                      fontWeight: 600, fontSize: 13, outline: "none", cursor: "pointer",
                      WebkitAppearance: "none", MozAppearance: "none", appearance: "none"
                    }}
                  >
                    <option value="pending" style={{ background: "var(--bg3)", color: "var(--text)" }}>Pending</option>
                    <option value="interview" style={{ background: "var(--bg3)", color: "var(--text)" }}>Interview</option>
                    <option value="offer" style={{ background: "var(--bg3)", color: "var(--text)" }}>Offer</option>
                    <option value="rejected" style={{ background: "var(--bg3)", color: "var(--text)" }}>Rejected</option>
                  </select>
                </div>
              </div>

              {/* Actions */}
              <div style={{ display: "flex", gap: 8 }}>
                <a href={`${API_BASE}/files/CV_job_${app.job_id}.pdf`} target="_blank" title="View CV"
                  className="btn btn-ghost btn-sm" style={{ padding: 8 }}>
                  <ExternalLink size={16} />
                </a>
                <button 
                  className="btn btn-danger btn-sm" 
                  style={{ padding: 8 }}
                  title="Delete Application"
                  onClick={() => {
                    if (confirm("Delete this application record?")) {
                      deleteMutation.mutate(app.id);
                    }
                  }}
                >
                  <Trash2 size={16} />
                </button>
              </div>

            </div>
          ))}
        </div>
      )}
    </div>
  );
}
