"use client";
import { Job, SOURCE_COLORS, SPONSORSHIP_META } from "@/lib/types";
import Link from "next/link";
import { MapPin, ExternalLink, Building2, AlertTriangle } from "lucide-react";
import FeedbackButtons from "./FeedbackButtons";

function PendingRing() {
  return (
    <div className="score-ring" title="Not assessed yet — waiting for the AI check">
      <svg width={52} height={52} viewBox="0 0 52 52">
        <circle cx={26} cy={26} r={22} fill="none" stroke="rgba(255,255,255,0.12)" strokeWidth={3} strokeDasharray="3 4" />
      </svg>
      <span className="score-label" style={{ fontSize: 9, lineHeight: 1.1, textAlign: "center", color: "var(--text3)" }}>
        <span>pending<br />AI check</span>
      </span>
    </div>
  );
}

function ScoreRing({ score }: { score: number }) {
  const r = 22, stroke = 3;
  const circ = 2 * Math.PI * r;
  const filled = (score / 100) * circ;
  const color = score >= 70 ? "#10b981" : score >= 50 ? "#f59e0b" : "#ef4444";
  return (
    <div className="score-ring">
      <svg width={52} height={52} viewBox="0 0 52 52">
        <circle cx={26} cy={26} r={r} fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth={stroke} />
        <circle cx={26} cy={26} r={r} fill="none" stroke={color} strokeWidth={stroke}
          strokeDasharray={`${filled} ${circ}`} strokeLinecap="round" />
      </svg>
      <span className="score-label">{score}%</span>
    </div>
  );
}

function scoreBadgeClass(score: number) {
  if (score >= 70) return "badge badge-score-high";
  if (score >= 50) return "badge badge-score-mid";
  return "badge badge-score-low";
}

interface Props {
  job: Job;
  onApply?: (job: Job) => void;
  onFeedback?: (jobId: number, feedback: number, reason?: string) => void;
}

export default function JobCard({ job, onApply, onFeedback }: Props) {
  const sourceColor = SOURCE_COLORS[job.source] || SOURCE_COLORS.default;
  const sponsor = job.sponsorship ? SPONSORSHIP_META[job.sponsorship] : undefined;
  const dealbreakers = job.dealbreakers ?? [];

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Header row */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <Link href={`/jobs/detail?id=${job.id}`} style={{ textDecoration: "none" }}>
            <h3 style={{ fontSize: 15, fontWeight: 700, color: "var(--text)", marginBottom: 4,
              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {job.title}
            </h3>
          </Link>
          <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--text2)", fontSize: 13 }}>
            <Building2 size={13} />
            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{job.company}</span>
          </div>
        </div>
        {job.assessed && job.fit_score != null ? <ScoreRing score={Math.round(job.fit_score)} /> : <PendingRing />}
      </div>

      {/* Meta */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
        <span className="badge badge-source" style={{ borderColor: sourceColor + "44", color: sourceColor }}>
          {job.source}
        </span>
        {job.location && (
          <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, color: "var(--text2)" }}>
            <MapPin size={11} /> {job.location}
          </span>
        )}
        {job.job_type && (
          <span className="badge badge-source" style={{ textTransform: "capitalize" }}>{job.job_type}</span>
        )}
        {sponsor && (
          <span className="badge badge-source" style={{ borderColor: sponsor.color + "55", color: sponsor.color }}>
            {sponsor.label}
          </span>
        )}
        {job.is_applied && <span className="badge badge-applied">✓ Applied</span>}
      </div>

      {/* AI verdict, else keyword reason */}
      {job.ai_verdict ? (
        <p style={{ fontSize: 12.5, color: "var(--text2)", lineHeight: 1.5,
          overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical" as any }}>
          <span style={{ color: "var(--accent2)", fontWeight: 600 }}>AI:</span> {job.ai_verdict}
        </p>
      ) : job.match_reasons?.length > 0 && (
        <p style={{ fontSize: 12, color: "var(--text2)", lineHeight: 1.5,
          overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" as any }}>
          {job.match_reasons[0]}
        </p>
      )}

      {/* Dealbreakers */}
      {dealbreakers.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {dealbreakers.slice(0, 3).map((d, i) => (
            <span key={i} style={{ display: "flex", alignItems: "flex-start", gap: 6, fontSize: 12, color: "var(--red)" }}>
              <AlertTriangle size={12} style={{ marginTop: 2, flexShrink: 0 }} /> {d}
            </span>
          ))}
        </div>
      )}

      {/* Feedback + actions */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8, marginTop: "auto" }}>
        {onFeedback && (
          <FeedbackButtons feedback={job.feedback}
            onRate={(fb, reason) => onFeedback(job.id, fb, reason)} />
        )}
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <Link href={`/jobs/detail?id=${job.id}`} className="btn btn-ghost btn-sm" style={{ flex: 1, justifyContent: "center" }}>
          Details
        </Link>
        <a href={job.url} target="_blank" rel="noopener noreferrer"
          className="btn btn-ghost btn-sm" title="Open job posting">
          <ExternalLink size={14} />
        </a>
        {onApply && (
          <button
            onClick={() => onApply(job)}
            className={job.is_applied ? "btn btn-ghost btn-sm" : "btn btn-primary btn-sm"}
            title={job.is_applied ? "Undo — mark as not applied" : "Mark as applied (you applied outside the app)"}
          >
            {job.is_applied ? "Applied ✓" : "Mark Applied"}
          </button>
        )}
      </div>
    </div>
  );
}
