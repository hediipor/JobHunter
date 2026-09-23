"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import api from "@/lib/api";
import { Job, countryOf } from "@/lib/types";
import JobCard from "@/components/JobCard";
import { Search, SlidersHorizontal } from "lucide-react";
import toast from "react-hot-toast";

export default function JobsPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [source, setSource] = useState("");
  const [minScore, setMinScore] = useState(0);
  const [jobType, setJobType] = useState("");
  const [country, setCountry] = useState("");
  const [sponsorship, setSponsorship] = useState("");

  const params = new URLSearchParams();
  if (source) params.set("source", source);
  if (minScore) params.set("min_score", String(minScore));
  if (sponsorship) params.set("sponsorship", sponsorship);

  const { data: jobs = [], isLoading } = useQuery<Job[]>({
    queryKey: ["jobs", source, minScore, sponsorship],
    queryFn: () => api.get(`/jobs/?${params}`),
  });

  const markAppliedMutation = useMutation({
    mutationFn: (jobId: number) => api.post(`/jobs/${jobId}/mark-applied`),
    onSuccess: (updated: Job) => {
      toast.success(updated.is_applied ? "Marked as applied" : "Unmarked");
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      qc.invalidateQueries({ queryKey: ["applications"] });
    },
    onError: () => toast.error("Couldn't update — is the backend running?"),
  });

  const feedbackMutation = useMutation({
    mutationFn: ({ jobId, feedback, reason }: { jobId: number; feedback: number; reason?: string }) =>
      api.patch(`/jobs/${jobId}/feedback`, { feedback, reason }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
    onError: () => toast.error("Couldn't save feedback"),
  });

  const countries = Array.from(new Set(jobs.map(countryOf).filter(Boolean))).sort();

  const filtered = jobs.filter(j => {
    const q = search.toLowerCase();
    const matchSearch = !q || j.title.toLowerCase().includes(q) || j.company.toLowerCase().includes(q) || j.location.toLowerCase().includes(q);
    const matchType = !jobType || (j.job_type || "").toLowerCase().includes(jobType);
    const matchCountry = !country || countryOf(j) === country;
    return matchSearch && matchType && matchCountry;
  });

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Job Board</h1>
        <p className="page-subtitle">{jobs.length} opportunities found matching your profile</p>
      </div>

      {/* Filters */}
      <div className="card" style={{ marginBottom: 24, display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
        <SlidersHorizontal size={16} color="var(--text2)" />
        <div style={{ position: "relative", flex: "1 1 200px" }}>
          <Search size={15} style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--text3)" }} />
          <input
            className="input"
            placeholder="Search title, company, location…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{ paddingLeft: 36 }}
          />
        </div>
        <select className="input" style={{ flex: "0 1 150px" }} value={source} onChange={e => setSource(e.target.value)}>
          <option value="">All Sources</option>
          <option value="linkedin">LinkedIn</option>
          <option value="indeed">Indeed</option>
          <option value="glassdoor">Glassdoor</option>
          <option value="keejob">Keejob</option>
        </select>
        <select className="input" style={{ flex: "0 1 150px" }} value={country} onChange={e => setCountry(e.target.value)}>
          <option value="">All Countries</option>
          {countries.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select className="input" style={{ flex: "0 1 150px" }} value={jobType} onChange={e => setJobType(e.target.value)}>
          <option value="">All Types</option>
          <option value="internship">Internship</option>
          <option value="full-time">Full-time</option>
          <option value="remote">Remote</option>
          <option value="part-time">Part-time</option>
        </select>
        <select className="input" style={{ flex: "0 1 170px" }} value={sponsorship} onChange={e => setSponsorship(e.target.value)}>
          <option value="">Any Sponsorship</option>
          <option value="yes,likely">Sponsors / likely</option>
          <option value="yes">Sponsors / remote-OK</option>
          <option value="unclear">Unclear</option>
          <option value="no">No sponsorship</option>
        </select>
        <select className="input" style={{ flex: "0 1 160px" }} value={minScore} onChange={e => setMinScore(Number(e.target.value))}>
          <option value={0}>Any Fit Score</option>
          <option value={50}>≥ 50% Fit</option>
          <option value={70}>≥ 70% Fit</option>
          <option value={85}>≥ 85% Fit</option>
        </select>
      </div>

      {/* Results */}
      {isLoading ? <div className="spinner" /> : filtered.length === 0 ? (
        <div className="empty">
          <h3>No jobs found</h3>
          <p>Try adjusting filters or run a new scan from the Dashboard.</p>
        </div>
      ) : (
        <div className="grid-3">
          {filtered.map(j => (
            <JobCard key={j.id} job={j} onApply={job => markAppliedMutation.mutate(job.id)}
              onFeedback={(jobId, feedback, reason) => feedbackMutation.mutate({ jobId, feedback, reason })} />
          ))}
        </div>
      )}
    </div>
  );
}
