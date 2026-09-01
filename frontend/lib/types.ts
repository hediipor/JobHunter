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
  description?: string;
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
