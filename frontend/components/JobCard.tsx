"use client";
import { Job, SOURCE_COLORS } from "@/lib/types";
import Link from "next/link";
import { MapPin, ExternalLink, Building2 } from "lucide-react";

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

interface Props { job: Job; onApply?: (job: Job) => void; }

export default function JobCard({ job, onApply }: Props) {
  const sourceColor = SOURCE_COLORS[job.source] || SOURCE_COLORS.default;

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Header row */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <Link href={`/jobs/${job.id}`} style={{ textDecoration: "none" }}>
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
        <ScoreRing score={Math.round(job.match_score)} />
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
        {job.is_applied && <span className="badge badge-applied">✓ Applied</span>}
      </div>

      {/* Reasons */}
      {job.match_reasons?.length > 0 && (
        <p style={{ fontSize: 12, color: "var(--text2)", lineHeight: 1.5,
          overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" as any }}>
          {job.match_reasons[0]}
        </p>
      )}

      {/* Actions */}
      <div style={{ display: "flex", gap: 8, marginTop: "auto" }}>
        <Link href={`/jobs/${job.id}`} className="btn btn-ghost btn-sm" style={{ flex: 1, justifyContent: "center" }}>
          Details
        </Link>
        <a href={job.url} target="_blank" rel="noopener noreferrer"
          className="btn btn-ghost btn-sm" title="Open job posting">
          <ExternalLink size={14} />
        </a>
        {!job.is_applied && onApply && (
          <button onClick={() => onApply(job)} className="btn btn-primary btn-sm">
            Apply
          </button>
        )}
      </div>
    </div>
  );
}
