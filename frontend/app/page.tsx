"use client";
import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api";
import { Stats, Job, LlmProvider } from "@/lib/types";
import StatsCard from "@/components/StatsCard";
import JobCard from "@/components/JobCard";
import { Briefcase, Send, MessageSquare, Gift, Star, RefreshCw, Loader2, Mail, Sparkles } from "lucide-react";
import toast from "react-hot-toast";

interface ScanStatus { running: boolean; added: number | null; error: string | null; }

export default function Dashboard() {
  const qc = useQueryClient();
  const [watching, setWatching] = useState(false);

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
    onSuccess: (d: any) => {
      if (d?.message === "A scan is already running") {
        toast(d.message);
      } else {
        toast.success("🔍 Scan started — this can take a few minutes (scraping + AI check).");
      }
      setWatching(true);
    },
    onError: () => toast.error("Scan failed — is the backend running?"),
  });

  // Scraping + per-job AI triage can run for minutes, so poll actual status
  // instead of guessing with a fixed timer — that's what made "is it done yet?"
  // unclear before: the button re-enabled the instant the request was *queued*,
  // not when the scan actually finished.
  // Shares the settings page's query — only llm_providers is read here.
  const { data: llm } = useQuery<{ llm_providers: LlmProvider[] }>({
    queryKey: ["settings"],
    queryFn: () => api.get("/settings/"),
    refetchInterval: watching ? 15000 : false,
  });
  const providers = (llm?.llm_providers || []).filter(p => p.configured);

  const { data: scanStatus } = useQuery<ScanStatus>({
    queryKey: ["scan-status"],
    queryFn: () => api.get("/jobs/scan-status"),
    refetchInterval: watching ? 3000 : false,
  });

  useEffect(() => {
    if (!watching || scanStatus?.running !== false) return;
    setWatching(false);
    if (scanStatus.error) {
      toast.error(`Scan failed: ${scanStatus.error}`);
    } else {
      toast.success(
        scanStatus.added ? `✅ Scan complete — ${scanStatus.added} new job(s) found.` : "✅ Scan complete — no new jobs this time."
      );
    }
    qc.invalidateQueries({ queryKey: ["stats"] });
    qc.invalidateQueries({ queryKey: ["settings"] });
    qc.invalidateQueries({ queryKey: ["top-jobs"] });
    qc.invalidateQueries({ queryKey: ["jobs"] });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [watching, scanStatus]);

  // A scan already running when the dashboard loads (scheduled scan, or
  // started from another tab) — pick up watching it too.
  useEffect(() => {
    if (scanStatus?.running) setWatching(true);
  }, [scanStatus?.running]);

  const markAppliedMutation = useMutation({
    mutationFn: (jobId: number) => api.post(`/jobs/${jobId}/mark-applied`),
    onSuccess: (updated: Job) => {
      toast.success(updated.is_applied ? "Marked as applied" : "Unmarked");
      qc.invalidateQueries({ queryKey: ["top-jobs"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      qc.invalidateQueries({ queryKey: ["applications"] });
    },
    onError: () => toast.error("Couldn't update — is the backend running?"),
  });

  const digestMutation = useMutation({
    mutationFn: () => api.post("/stats/digest"),
    onSuccess: (d: any) => toast.success(d?.message || "📧 Digest sent to your inbox"),
    onError: () => toast.error("Digest failed — no recent jobs, or Gmail not configured."),
  });

  const triageMutation = useMutation({
    mutationFn: () => api.post("/jobs/triage-pending"),
    onSuccess: (d: any) => toast.success(d?.message || "🤖 Assessing jobs…", { duration: 6000 }),
    onError: () => toast.error("Triage failed — check your API keys or quota."),
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
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button
            className="btn btn-ghost"
            onClick={() => triageMutation.mutate()}
            disabled={triageMutation.isPending}
          >
            {triageMutation.isPending
              ? <><Loader2 size={16} style={{ animation: "spin 0.7s linear infinite" }} /> Assessing…</>
              : <><Sparkles size={16} /> Run AI Check</>
            }
          </button>
          <button
            className="btn btn-ghost"
            onClick={() => digestMutation.mutate()}
            disabled={digestMutation.isPending}
          >
            {digestMutation.isPending
              ? <><Loader2 size={16} style={{ animation: "spin 0.7s linear infinite" }} /> Sending…</>
              : <><Mail size={16} /> Email Me a Digest</>
            }
          </button>
          <button
            className="btn btn-primary"
            onClick={() => scanMutation.mutate()}
            disabled={scanMutation.isPending || watching}
            title={watching ? "Scraping + AI check in progress — this can take a few minutes" : undefined}
          >
            {scanMutation.isPending || watching
              ? <><Loader2 size={16} style={{ animation: "spin 0.7s linear infinite" }} /> Scanning…</>
              : <><RefreshCw size={16} /> Scan Jobs Now</>
            }
          </button>
        </div>
      </div>

      {/* LLM quota — otherwise the only sign you're out is a log line */}
      {llm && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 20, fontSize: 12 }}>
          {providers.length === 0 && (
            <span className="badge badge-score-low">No LLM key configured — AI check is off</span>
          )}
          {providers.map(p => (
            <span key={p.name} title={p.model}
              className={`badge ${p.exhausted ? "badge-score-low" : "badge-source"}`}>
              {p.name}: {p.used_today}{p.daily_cap ? `/${p.daily_cap}` : ""} today
              {p.exhausted && " · out of quota until 00:00 UTC"}
            </span>
          ))}
        </div>
      )}

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
            {topJobsList.map(j => (
              <JobCard key={j.id} job={j} onApply={job => markAppliedMutation.mutate(job.id)} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
