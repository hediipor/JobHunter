"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api";
import { Stats, Job } from "@/lib/types";
import StatsCard from "@/components/StatsCard";
import JobCard from "@/components/JobCard";
import { Briefcase, Send, MessageSquare, Gift, Star, RefreshCw, Loader2 } from "lucide-react";
import toast from "react-hot-toast";

export default function Dashboard() {
  const qc = useQueryClient();

  const { data: stats, isLoading: statsLoading } = useQuery<Stats>({
    queryKey: ["stats"],
    queryFn: () => api.get("/stats/"),
  });

  const { data: topJobs } = useQuery<Job[]>({
    queryKey: ["top-jobs"],
    queryFn: () => api.get("/jobs/?min_score=60"),
  });

  const scanMutation = useMutation({
    mutationFn: () => api.post("/jobs/scan"),
    onSuccess: () => {
      toast.success("🔍 Scan started! New jobs will appear shortly.");
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ["stats"] });
        qc.invalidateQueries({ queryKey: ["top-jobs"] });
        qc.invalidateQueries({ queryKey: ["jobs"] });
      }, 8000);
    },
    onError: () => toast.error("Scan failed — is the backend running?"),
  });

  const topJobsList = (topJobs || []).slice(0, 6);

  return (
    <div>
      {/* Header */}
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h1 className="page-title">
            Good morning, <span className="gradient-text">Hedi</span> 👋
          </h1>
          <p className="page-subtitle">Here's your job hunt overview</p>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => scanMutation.mutate()}
          disabled={scanMutation.isPending}
        >
          {scanMutation.isPending
            ? <><Loader2 size={16} style={{ animation: "spin 0.7s linear infinite" }} /> Scanning…</>
            : <><RefreshCw size={16} /> Scan Jobs Now</>
          }
        </button>
      </div>

      {/* Stats */}
      {statsLoading ? <div className="spinner" /> : stats && (
        <>
          <div className="grid-4" style={{ marginBottom: 28 }}>
            <StatsCard label="Jobs Found" value={stats.total_jobs} icon={Briefcase} color="var(--accent)" />
            <StatsCard label="Applications Sent" value={stats.applied} icon={Send} color="var(--accent2)" />
            <StatsCard label="Interviews" value={stats.interviews} icon={MessageSquare} color="var(--yellow)" />
            <StatsCard label="Offers" value={stats.offers} icon={Gift} color="var(--green)" />
          </div>

          {/* Score & Sources row */}
          <div className="grid-2" style={{ marginBottom: 28 }}>
            {/* Score distribution */}
            <div className="card">
              <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 16 }}>Match Score Distribution</h3>
              {Object.entries(stats.score_distribution).map(([range, count]) => {
                const pct = stats.total_jobs ? Math.round((count / stats.total_jobs) * 100) : 0;
                const color = range === "90-100" ? "var(--green)" : range === "70-89" ? "var(--accent2)" : range === "50-69" ? "var(--yellow)" : "var(--red)";
                return (
                  <div key={range} style={{ marginBottom: 10 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 4, color: "var(--text2)" }}>
                      <span>{range}%</span><span>{count} jobs</span>
                    </div>
                    <div style={{ height: 6, background: "var(--bg3)", borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ height: "100%", width: `${pct}%`, background: color, borderRadius: 3, transition: "width 0.5s" }} />
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Sources */}
            <div className="card">
              <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 16 }}>Jobs by Source</h3>
              {Object.entries(stats.sources).length === 0
                ? <p style={{ color: "var(--text2)", fontSize: 13 }}>No data yet — run a scan first.</p>
                : Object.entries(stats.sources).map(([src, count]) => (
                <div key={src} style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
                  padding: "10px 0", borderBottom: "1px solid var(--glass-border)" }}>
                  <span style={{ fontSize: 14, textTransform: "capitalize" }}>{src}</span>
                  <span className="badge badge-source">{count}</span>
                </div>
              ))}
              <div style={{ marginTop: 16, padding: "10px 14px", background: "rgba(99,102,241,0.08)",
                borderRadius: 8, fontSize: 13, color: "var(--text2)" }}>
                ⚡ Avg match score: <strong style={{ color: "var(--accent)" }}>{stats.avg_score}%</strong>
              </div>
            </div>
          </div>
        </>
      )}

      {/* Top matching jobs */}
      <div>
        <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 16, display: "flex", alignItems: "center", gap: 8 }}>
          <Star size={18} color="var(--yellow)" /> Top Matching Jobs
        </h2>
        {topJobsList.length === 0 ? (
          <div className="empty">
            <h3>No jobs yet</h3>
            <p>Click <strong>Scan Jobs Now</strong> to discover opportunities matching your profile.</p>
          </div>
        ) : (
          <div className="grid-3">
            {topJobsList.map(j => <JobCard key={j.id} job={j} />)}
          </div>
        )}
      </div>
    </div>
  );
}
