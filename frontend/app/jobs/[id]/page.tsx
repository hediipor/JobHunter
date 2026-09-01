"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import api, { API_BASE } from "@/lib/api";
import { Job } from "@/lib/types";
import { ArrowLeft, ExternalLink, FileText, Mail, Send, Loader2, MapPin, Building2, Zap } from "lucide-react";
import toast from "react-hot-toast";

export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [applyEmail, setApplyEmail] = useState("");
  const [showApplyBox, setShowApplyBox] = useState(false);

  const { data: job, isLoading } = useQuery<Job>({
    queryKey: ["job", id],
    queryFn: () => api.get(`/jobs/${id}`),
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

  if (isLoading) return <div className="spinner" />;
  if (!job) return <div className="empty"><h3>Job not found</h3></div>;

  const score = Math.round(job.match_score);
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
