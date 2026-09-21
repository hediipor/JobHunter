"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, useEffect } from "react";
import api from "@/lib/api";
import { Save, Key, Zap, Bell, Search, MapPin, CheckCircle2, XCircle, Globe } from "lucide-react";
import toast from "react-hot-toast";

interface SourceSettings { enabled: boolean; queries: number }

// What each source's "requests per scan" costs — shown under its toggle.
const SOURCE_INFO: Record<string, { label: string; hint: string }> = {
  jsearch: { label: "JSearch (LinkedIn, Indeed, Glassdoor…)", hint: "RapidAPI requests per scan — free tier is 200/month." },
  keejob: { label: "Keejob (Tunisia)", hint: "Pages scraped per scan, using its own French search terms." },
};

interface AppSettings {
  scan_interval_hours: number;
  max_jobs_per_scan: number;
  search_terms: string[];
  locations: string[];
  sources: Record<string, SourceSettings>;
  keys: { gemini: boolean; groq: boolean; gmail: boolean; rapidapi: boolean };
  gmail_from: string;
}

function KeyStatus({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: "1px solid var(--glass-border)" }}>
      <span style={{ fontSize: 14 }}>{label}</span>
      {ok ? (
        <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 13, color: "var(--green)" }}>
          <CheckCircle2 size={14} /> Configured
        </span>
      ) : (
        <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 13, color: "var(--red)" }}>
          <XCircle size={14} /> Missing
        </span>
      )}
    </div>
  );
}

export default function SettingsPage() {
  const qc = useQueryClient();
  const [interval, setIntervalHours] = useState("24");
  const [maxJobs, setMaxJobs] = useState("50");
  const [terms, setTerms] = useState("");
  const [locations, setLocations] = useState("");
  const [sources, setSources] = useState<Record<string, SourceSettings>>({});
  const [loaded, setLoaded] = useState(false);

  const { data: cfg, isLoading } = useQuery<AppSettings>({
    queryKey: ["settings"],
    queryFn: () => api.get("/settings/"),
  });

  useEffect(() => {
    if (cfg && !loaded) {
      setIntervalHours(String(cfg.scan_interval_hours));
      setMaxJobs(String(cfg.max_jobs_per_scan));
      setTerms(cfg.search_terms.join("\n"));
      setLocations(cfg.locations.join("\n"));
      setSources(cfg.sources);
      setLoaded(true);
    }
  }, [cfg, loaded]);

  const saveMutation = useMutation({
    mutationFn: (body: object) => api.put("/settings/", body),
    onSuccess: () => {
      toast.success("Settings saved — scan schedule updated!");
      qc.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: () => toast.error("Failed to save settings. Is the backend running?"),
  });

  const handleSave = () => {
    const hours = parseInt(interval, 10);
    const jobs = parseInt(maxJobs, 10);
    if (isNaN(hours) || hours < 1 || hours > 168) {
      toast.error("Scan interval must be between 1 and 168 hours.");
      return;
    }
    if (isNaN(jobs) || jobs < 1 || jobs > 200) {
      toast.error("Max jobs per scan must be between 1 and 200.");
      return;
    }
    if (!Object.values(sources).some(s => s.enabled)) {
      toast.error("Enable at least one job source.");
      return;
    }
    if (Object.values(sources).some(s => !Number.isInteger(s.queries) || s.queries < 1 || s.queries > 50)) {
      toast.error("Requests per scan must be between 1 and 50.");
      return;
    }
    saveMutation.mutate({
      scan_interval_hours: hours,
      max_jobs_per_scan: jobs,
      search_terms: terms.split("\n").map(t => t.trim()).filter(Boolean),
      locations: locations.split("\n").map(l => l.trim()).filter(Boolean),
      sources,
    });
  };

  if (isLoading) return <div className="spinner" />;

  return (
    <div>
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h1 className="page-title">Settings</h1>
          <p className="page-subtitle">Configure your JobHunter AI preferences</p>
        </div>
        <button className="btn btn-primary" onClick={handleSave} disabled={saveMutation.isPending}>
          <Save size={16} /> Save Settings
        </button>
      </div>

      <div className="grid-2">
        {/* Scan schedule */}
        <div className="card">
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
            <Bell size={18} color="var(--accent2)" />
            <h3 style={{ fontSize: 16, fontWeight: 700 }}>Scan Schedule</h3>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 6, color: "var(--text2)" }}>
                Scan interval (hours)
              </label>
              <input type="number" min={1} max={168} className="input" value={interval}
                onChange={e => setIntervalHours(e.target.value)} />
              <p style={{ fontSize: 12, color: "var(--text2)", marginTop: 6 }}>
                Each scan uses up to {sources.jsearch?.queries ?? 10} JSearch API requests (free tier: 200/month) — at 10 per scan, use a 48h+ interval on the free plan.
              </p>
            </div>
            <div>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 6, color: "var(--text2)" }}>
                Max jobs per scan
              </label>
              <input type="number" min={1} max={200} className="input" value={maxJobs}
                onChange={e => setMaxJobs(e.target.value)} />
              <p style={{ fontSize: 12, color: "var(--text2)", marginTop: 6 }}>
                Split evenly between the enabled sources. Every new job gets an AI check, so this is also the scan&apos;s AI budget.
              </p>
            </div>
          </div>
        </div>

        {/* Job sources */}
        <div className="card">
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
            <Globe size={18} color="var(--accent)" />
            <h3 style={{ fontSize: 16, fontWeight: 700 }}>Job Sources</h3>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {Object.entries(sources).map(([name, s]) => (
              <div key={name}>
                <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 14, fontWeight: 600 }}>
                  <input type="checkbox" checked={s.enabled}
                    onChange={e => setSources({ ...sources, [name]: { ...s, enabled: e.target.checked } })} />
                  {SOURCE_INFO[name]?.label ?? name}
                </label>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6, marginLeft: 24 }}>
                  <input type="number" min={1} max={50} className="input" style={{ width: 90 }}
                    aria-label={`${name} requests per scan`} value={Number.isNaN(s.queries) ? "" : s.queries} disabled={!s.enabled}
                    onChange={e => setSources({ ...sources, [name]: { ...s, queries: parseInt(e.target.value, 10) } })} />
                  <span style={{ fontSize: 12, color: "var(--text2)" }}>{SOURCE_INFO[name]?.hint ?? "Requests per scan."}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* API keys — read-only status */}
        <div className="card">
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
            <Key size={18} color="var(--accent)" />
            <h3 style={{ fontSize: 16, fontWeight: 700 }}>API Keys</h3>
          </div>
          <KeyStatus label="Gemini API key" ok={!!cfg?.keys.gemini} />
          <KeyStatus label="Groq API key" ok={!!cfg?.keys.groq} />
          <KeyStatus label="RapidAPI key (JSearch)" ok={!!cfg?.keys.rapidapi} />
          <KeyStatus label={`Gmail app password (${cfg?.gmail_from || "not set"})`} ok={!!cfg?.keys.gmail} />
          <p style={{ fontSize: 12, color: "var(--text2)", marginTop: 10 }}>
            The per-job AI check (fit score, visa sponsorship, dealbreakers) runs on Groq first,
            falling back to Gemini; CVs and cover letters run on Gemini first, falling back to
            Groq. Either key alone works. Each scan assesses every new job; if the day&apos;s
            quota runs out first, the rest show as &quot;pending AI check&quot; and can be filled
            in from the dashboard.
          </p>
          <p style={{ fontSize: 12, color: "var(--text2)", marginTop: 12 }}>
            Keys are stored in the backend <code style={{ background: "var(--bg)", padding: "2px 6px", borderRadius: 4 }}>.env</code> file.
            Edit that file and restart the backend to change them.
          </p>
        </div>

        {/* Search terms */}
        <div className="card">
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
            <Search size={18} color="var(--yellow)" />
            <h3 style={{ fontSize: 16, fontWeight: 700 }}>Search Terms</h3>
          </div>
          <p style={{ fontSize: 13, color: "var(--text2)", marginBottom: 10 }}>
            One per line. Every term is used: each scan picks up the term × location pairs where the last one stopped.
          </p>
          <textarea className="input" value={terms} onChange={e => setTerms(e.target.value)}
            spellCheck={false}
            style={{ minHeight: 180, resize: "vertical", fontFamily: "monospace", fontSize: 13, lineHeight: 1.7 }} />
        </div>

        {/* Locations */}
        <div className="card">
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
            <MapPin size={18} color="var(--green)" />
            <h3 style={{ fontSize: 16, fontWeight: 700 }}>Locations</h3>
          </div>
          <p style={{ fontSize: 13, color: "var(--text2)", marginBottom: 10 }}>
            One per line. Country name, “City, Country”, or “Remote”. Keejob covers Tunisia separately.
          </p>
          <textarea className="input" value={locations} onChange={e => setLocations(e.target.value)}
            spellCheck={false}
            style={{ minHeight: 180, resize: "vertical", fontFamily: "monospace", fontSize: 13, lineHeight: 1.7 }} />
        </div>
      </div>
    </div>
  );
}
