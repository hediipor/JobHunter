"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import api, { API_BASE } from "@/lib/api";
import { Job, SPONSORSHIP_META, effectiveScore } from "@/lib/types";
import { ArrowLeft, ExternalLink, FileText, Mail, Send, Loader2, MapPin, Building2, Zap, Sparkles, AlertTriangle } from "lucide-react";
import toast from "react-hot-toast";

function JobDetailContent() {
  const id = useSearchParams().get("id");
  const qc = useQueryClient();
  const [applyEmail, setApplyEmail] = useState("");
  const [showApplyBox, setShowApplyBox] = useState(false);

  const { data: job, isLoading } = useQuery<Job>({
    queryKey: ["job", id],
    queryFn: () => api.get(`/jobs/${id}`),
    enabled: !!id,
  });

  const genMutation = useMutation({
    mutationFn: () => api.post(`/jobs/${id}/generate`),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["job", id] });
      toast.success("📄 CV & Cover Letter generated!");
    },
    onError: () => toast.error("Generation failed — check your Gemini API key."),
  });

  const applyMutation = useMutation({
    mutationFn: () => api.post(`/jobs/${id}/apply`, { to_email: applyEmail }),
    onSuccess: () => {
      toast.success("✉️ Application email sent!");
      setShowApplyBox(false);
      qc.invalidateQueries({ queryKey: ["job", id] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
    onError: (err: any) => toast.error("Email failed — check Gmail settings."),
  });

  const triageMutation = useMutation({
    mutationFn: () => api.post(`/jobs/${id}/triage`),
    onSuccess: () => {
      toast.success("🤖 AI assessment updated");
      qc.invalidateQueries({ queryKey: ["job", id] });
    },
    onError: () => toast.error("Triage failed — check your Gemini API key."),
  });

  const markAppliedMutation = useMutation({
    mutationFn: () => api.post(`/jobs/${id}/mark-applied`),
    onSuccess: (updated: Job) => {
      toast.success(updated.is_applied ? "Marked as applied" : "Unmarked");
      qc.invalidateQueries({ queryKey: ["job", id] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      qc.invalidateQueries({ queryKey: ["applications"] });
    },
    onError: () => toast.error("Couldn't update — is the backend running?"),
  });

  if (!id) return <div className="empty"><h3>Job not found</h3></div>;
  if (isLoading) return <div className="spinner" />;
  if (!job) return <div className="empty"><h3>Job not found</h3></div>;

  const score = Math.round(effectiveScore(job));
  const sponsor = job.sponsorship ? SPONSORSHIP_META[job.sponsorship] : undefined;
  const dealbreakers = job.dealbreakers ?? [];
  const scoreColor = score >= 70 ? "var(--green)" : score >= 50 ? "var(--yellow)" : "var(--red)";
  const circ = 2 * Math.PI * 38;
  const filled = (score / 100) * circ;

  return (
    <div>
      {/* Back */}
      <Link href="/jobs" className="btn btn-ghost btn-sm" style={{ marginBottom: 20 }}>
        <ArrowLeft size={15} /> Back to Jobs
      </Link>

      <div className="grid-2" style={{ alignItems: "start" }}>
        {/* Left: details */}
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div className="card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16 }}>
              <div>
                <h1 style={{ fontSize: 22, fontWeight: 800, marginBottom: 6 }}>{job.title}</h1>
                <div style={{ display: "flex", gap: 12, color: "var(--text2)", fontSize: 14, flexWrap: "wrap" }}>
                  <span style={{ display: "flex", alignItems: "center", gap: 5 }}><Building2 size={14} />{job.company}</span>
                  <span style={{ display: "flex", alignItems: "center", gap: 5 }}><MapPin size={14} />{job.location}</span>
                </div>
              </div>
              {/* Big score ring */}
              <div style={{ position: "relative", width: 88, height: 88, flexShrink: 0 }}>
                <svg width={88} height={88} viewBox="0 0 88 88" style={{ transform: "rotate(-90deg)" }}>
                  <circle cx={44} cy={44} r={38} fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth={5} />
                  <circle cx={44} cy={44} r={38} fill="none" stroke={scoreColor} strokeWidth={5}
                    strokeDasharray={`${filled} ${circ}`} strokeLinecap="round" />
                </svg>
                <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column",
                  alignItems: "center", justifyContent: "center" }}>
                  <span style={{ fontSize: 20, fontWeight: 800, color: scoreColor }}>{score}%</span>
                  <span style={{ fontSize: 10, color: "var(--text2)" }}>Match</span>
                </div>
              </div>
            </div>

            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 16 }}>
              <span className="badge badge-source" style={{ textTransform: "capitalize" }}>{job.source}</span>
              {job.job_type && <span className="badge badge-source">{job.job_type}</span>}
              {job.salary && <span className="badge badge-source">💰 {job.salary}</span>}
              {job.is_applied && <span className="badge badge-applied">✓ Applied</span>}
            </div>
          </div>

          {/* AI assessment */}
          <div className="card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <h3 style={{ fontSize: 15, fontWeight: 700, display: "flex", alignItems: "center", gap: 6 }}>
                <Sparkles size={16} color="var(--accent2)" /> AI Assessment
              </h3>
              <button className="btn btn-ghost btn-sm" onClick={() => triageMutation.mutate()}
                disabled={triageMutation.isPending}>
                {triageMutation.isPending
                  ? <><Loader2 size={13} style={{ animation: "spin 0.7s linear infinite" }} /> Checking…</>
                  : (job.ai_verdict ? "Re-check" : "Run check")}
              </button>
            </div>
            {job.ai_verdict ? (
              <>
                <p style={{ fontSize: 14, color: "var(--text2)", lineHeight: 1.6, marginBottom: 12 }}>
                  {job.ai_verdict}
                </p>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: dealbreakers.length ? 12 : 0 }}>
                  {job.ai_score != null && (
                    <span className="badge badge-source">AI fit {Math.round(job.ai_score)}%</span>
                  )}
                  {sponsor && (
                    <span className="badge badge-source" style={{ borderColor: sponsor.color + "55", color: sponsor.color }}>
                      {sponsor.label}
                    </span>
                  )}
                </div>
                {dealbreakers.map((d, i) => (
                  <div key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start", padding: "6px 0",
                    fontSize: 13, color: "var(--red)" }}>
                    <AlertTriangle size={13} style={{ marginTop: 2, flexShrink: 0 }} /> {d}
                  </div>
                ))}
              </>
            ) : (
              <p style={{ fontSize: 13, color: "var(--text3)" }}>
                Not assessed yet. Gemini checks the top matches each scan — run it manually here.
              </p>
            )}
          </div>

          {/* Match reasons */}
          {job.match_reasons?.length > 0 && (
            <div className="card">
              <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 12, display: "flex", alignItems: "center", gap: 6 }}>
                <Zap size={16} color="var(--yellow)" /> Why This Matches Your Profile
              </h3>
              {job.match_reasons.map((r, i) => (
                <div key={i} style={{ display: "flex", gap: 10, alignItems: "flex-start",
                  padding: "8px 0", borderBottom: "1px solid var(--glass-border)" }}>
                  <span style={{ color: "var(--green)", marginTop: 1 }}>✓</span>
                  <span style={{ fontSize: 14, color: "var(--text2)" }}>{r}</span>
                </div>
              ))}
            </div>
          )}

          {/* Description */}
          {job.description && (
            <div className="card">
              <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 12 }}>Job Description</h3>
              <div style={{ fontSize: 14, color: "var(--text2)", lineHeight: 1.7, whiteSpace: "pre-wrap",
                maxHeight: 400, overflowY: "auto" }}>
                {job.description}
              </div>
            </div>
          )}
        </div>

        {/* Right: actions */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="card">
            <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 16 }}>Apply to this Job</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {/* Step 1: Generate */}
              <button className="btn btn-primary" onClick={() => genMutation.mutate()} disabled={genMutation.isPending}
                style={{ width: "100%", justifyContent: "center" }}>
                {genMutation.isPending
                  ? <><Loader2 size={16} style={{ animation: "spin 0.7s linear infinite" }} /> Generating…</>
                  : <><FileText size={16} /> Generate CV + Cover Letter</>
                }
              </button>

              {genMutation.isSuccess && (
                <div style={{ padding: "10px 12px", background: "rgba(16,185,129,0.08)",
                  border: "1px solid rgba(16,185,129,0.25)", borderRadius: 8, fontSize: 13, color: "var(--green)" }}>
                  ✓ Documents generated! Review below then send.
                  {genMutation.data?.cv_summary && (
                    <p style={{ marginTop: 6, color: "var(--text2)", fontStyle: "italic" }}>
                      "{genMutation.data.cv_summary}"
                    </p>
                  )}
                </div>
              )}

              {/* Step 2: Send */}
              {!showApplyBox ? (
                <button className="btn btn-cyan" onClick={() => setShowApplyBox(true)}
                  disabled={!genMutation.isSuccess && !job.is_applied}
                  style={{ width: "100%", justifyContent: "center" }}>
                  <Send size={16} /> Send Application Email
                </button>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <input
                    className="input"
                    placeholder="Recruiter email (e.g. hr@company.com)"
                    value={applyEmail}
                    onChange={e => setApplyEmail(e.target.value)}
                  />
                  <button className="btn btn-cyan" onClick={() => applyMutation.mutate()}
                    disabled={!applyEmail || applyMutation.isPending}
                    style={{ width: "100%", justifyContent: "center" }}>
                    {applyMutation.isPending
                      ? <><Loader2 size={16} style={{ animation: "spin 0.7s linear infinite" }} /> Sending…</>
                      : <><Send size={16} /> Confirm & Send</>
                    }
                  </button>
                  <button className="btn btn-ghost btn-sm" onClick={() => setShowApplyBox(false)}>Cancel</button>
                </div>
              )}

              <a href={job.url} target="_blank" rel="noopener noreferrer"
                className="btn btn-ghost" style={{ width: "100%", justifyContent: "center" }}>
                <ExternalLink size={15} /> View Original Posting
              </a>

              <div style={{ borderTop: "1px solid var(--glass-border)", paddingTop: 10, marginTop: 4 }}>
                <p style={{ fontSize: 12, color: "var(--text3)", marginBottom: 8 }}>
                  Applied on the company's site instead?
                </p>
                <button
                  className={job.is_applied ? "btn btn-ghost" : "btn btn-primary"}
                  onClick={() => markAppliedMutation.mutate()}
                  disabled={markAppliedMutation.isPending}
                  style={{ width: "100%", justifyContent: "center" }}
                >
                  {markAppliedMutation.isPending
                    ? <><Loader2 size={15} style={{ animation: "spin 0.7s linear infinite" }} /> Updating…</>
                    : job.is_applied ? "Undo — Not Applied" : "Mark as Applied"
                  }
                </button>
              </div>
            </div>
          </div>

          {/* PDF links if generated */}
          {genMutation.isSuccess && (
            <div className="card">
              <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 12 }}>Generated Documents</h3>
              <a href={`${API_BASE}/files/CV_job_${id}.pdf`} target="_blank"
                className="btn btn-ghost btn-sm" style={{ width: "100%", justifyContent: "center", marginBottom: 8 }}>
                <FileText size={14} /> Download CV (PDF)
              </a>
              <a href={`${API_BASE}/files/CL_job_${id}.pdf`} target="_blank"
                className="btn btn-ghost btn-sm" style={{ width: "100%", justifyContent: "center" }}>
                <Mail size={14} /> Download Cover Letter (PDF)
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function JobDetailPage() {
  return (
    <Suspense fallback={<div className="spinner" />}>
      <JobDetailContent />
    </Suspense>
  );
}
