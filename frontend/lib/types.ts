export interface Job {
  id: number;
  title: string;
  company: string;
  location: string;
  url: string;
  source: string;
  job_type: string;
  date_posted: string;
  salary: string;
  match_score: number;
  match_reasons: string[];
  status: string;
  is_applied: boolean;
  ai_score?: number | null;
  ai_verdict?: string;
  sponsorship?: string;   // yes | likely | unclear | no
  dealbreakers?: string[];
  description?: string;
}

// AI triage score if present, else the keyword score.
export const effectiveScore = (j: Pick<Job, "ai_score" | "match_score">): number =>
  j.ai_score != null ? j.ai_score : j.match_score;

export const SPONSORSHIP_META: Record<string, { label: string; color: string }> = {
  yes: { label: "Sponsors / remote-OK", color: "#10b981" },
  likely: { label: "Sponsorship likely", color: "#f59e0b" },
  unclear: { label: "Sponsorship unclear", color: "#94a3b8" },
  no: { label: "No sponsorship", color: "#ef4444" },
};

// One row of GET /settings/ -> llm_providers
export interface LlmProvider {
  name: string;
  model: string;
  configured: boolean;
  used_today: number;
  daily_cap: number | null;
  exhausted: boolean;
}

export interface Application {
  id: number;
  job_id: number;
  job_title: string;
  company: string;
  email_sent: boolean;
  response_status: string;  // pending | interview | offer | rejected
  notes: string;
  cv_path: string;
  cover_letter_path: string;
  email_subject: string;
}

export interface Stats {
  total_jobs: number;
  applied: number;
  interviews: number;
  offers: number;
  avg_score: number;
  sources: Record<string, number>;
  score_distribution: Record<string, number>;
  top_jobs: { id: number; title: string; company: string; score: number }[];
}

export const STATUS_LABELS: Record<string, string> = {
  new: "New",
  saved: "Saved",
  applied: "Applied",
  interview: "Interview",
  offer: "Offer",
  rejected: "Rejected",
  pending: "Pending",
};

export const SOURCE_COLORS: Record<string, string> = {
  linkedin: "#0077b5",
  indeed: "#003a9b",
  glassdoor: "#0caa41",
  keejob: "#e85d2b",
  default: "#6366f1",
};

// JSearch stores location as "City, XX" with a 2-letter country code; Keejob
// gives Tunisian towns with no code. Map both to a display country name.
const COUNTRY_NAMES: Record<string, string> = {
  FR: "France", ES: "Spain", DE: "Germany", CA: "Canada", TN: "Tunisia",
  NL: "Netherlands", GB: "United Kingdom", IE: "Ireland", PT: "Portugal",
  US: "United States", BE: "Belgium", CH: "Switzerland", IT: "Italy",
  AT: "Austria", SE: "Sweden", PL: "Poland",
};

export function countryOf(job: Pick<Job, "location" | "source">): string {
  if (job.source === "keejob") return "Tunisia";
  const loc = (job.location || "").trim();
  if (!loc) return "";
  if (/^remote$/i.test(loc)) return "Remote";
  const last = loc.split(/[,،]/).pop()!.trim();
  return COUNTRY_NAMES[last.toUpperCase()] || last;
}
