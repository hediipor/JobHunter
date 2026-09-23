"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api";
import toast from "react-hot-toast";
import { Rocket, ChevronRight, ChevronLeft, Eye, EyeOff } from "lucide-react";

const ADVANCED_TEMPLATE = `{
  "education": [{"degree": "", "institution": "", "period": "", "gpa": null}],
  "experience": [{"role": "", "company": "", "period": "", "location": "", "bullets": [""]}],
  "projects": [{"name": "", "description": "", "technologies": [], "highlights": []}]
}`;

function csv(s: string): string[] {
  return s.split(",").map(x => x.trim()).filter(Boolean);
}

function Field({ label, hint, ...props }: { label: string; hint?: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 6, color: "var(--text2)" }}>
        {label}
      </label>
      <input className="input" {...props} />
      {hint && <p style={{ fontSize: 12, color: "var(--text2)", marginTop: 6 }}>{hint}</p>}
    </div>
  );
}

export default function SetupPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [step, setStep] = useState(1);

  // Step 2 state
  const [showGemini, setShowGemini] = useState(false);
  const [geminiKey, setGeminiKey] = useState("");
  const [groqKey, setGroqKey] = useState("");
  const [openrouterKey, setOpenrouterKey] = useState("");
  const [rapidapiKey, setRapidapiKey] = useState("");
  const [gmailFrom, setGmailFrom] = useState("");
  const [gmailPassword, setGmailPassword] = useState("");

  // Step 3 state
  const [name, setName] = useState("");
  const [title, setTitle] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [location, setLocation] = useState("");
  const [portfolio, setPortfolio] = useState("");
  const [github, setGithub] = useState("");
  const [linkedin, setLinkedin] = useState("");
  const [languagesSpoken, setLanguagesSpoken] = useState("");
  const [interests, setInterests] = useState("");
  const [targetRoles, setTargetRoles] = useState("");
  const [targetLocations, setTargetLocations] = useState("");
  const [skillLangs, setSkillLangs] = useState("");
  const [skillFrameworks, setSkillFrameworks] = useState("");
  const [skillTools, setSkillTools] = useState("");
  const [skillDatabases, setSkillDatabases] = useState("");
  const [skillCerts, setSkillCerts] = useState("");
  const [skillCoursework, setSkillCoursework] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [advancedJson, setAdvancedJson] = useState(ADVANCED_TEMPLATE);

  const keysMutation = useMutation({
    mutationFn: (body: object) => api.post("/setup/keys", body),
    onSuccess: () => {
      toast.success("Keys saved");
      qc.invalidateQueries({ queryKey: ["setup-status"] });
      setStep(3);
    },
    onError: () => toast.error("Failed to save keys. Is the backend running?"),
  });

  const profileMutation = useMutation({
    mutationFn: (body: object) => api.put("/profile/", body),
    onSuccess: () => {
      toast.success("Profile saved — welcome to JobHunter AI!");
      // A full reload, not router.push: SetupGate's ["setup-status"] query stays
      // mounted (it lives in layout.tsx) and client-side nav in this statically
      // exported app re-renders the "/" route from an already-prefetched static
      // payload, so the gate can end up deciding on stale pre-save data and
      // bouncing straight back to /setup. Reloading guarantees a fresh mount
      // that fetches the real, just-saved status.
      window.location.href = "/";
    },
    onError: () => toast.error("Failed to save profile. Is the backend running?"),
  });

  const handleSaveKeys = () => {
    const body: Record<string, string> = {};
    if (geminiKey.trim()) body.gemini_api_key = geminiKey.trim();
    if (groqKey.trim()) body.groq_api_key = groqKey.trim();
    if (openrouterKey.trim()) body.openrouter_api_key = openrouterKey.trim();
    if (rapidapiKey.trim()) body.rapidapi_key = rapidapiKey.trim();
    if (gmailFrom.trim()) body.gmail_from = gmailFrom.trim();
    if (gmailPassword.trim()) body.gmail_app_password = gmailPassword.trim();
    if (Object.keys(body).length === 0) {
      setStep(3);
      return;
    }
    keysMutation.mutate(body);
  };

  const handleFinish = () => {
    let advanced: { education?: unknown[]; experience?: unknown[]; projects?: unknown[] };
    try {
      advanced = JSON.parse(advancedJson || "{}");
    } catch {
      toast.error("Advanced JSON is invalid — fix it or leave the template as-is.");
      return;
    }
    if (!name.trim()) {
      toast.error("Name is required.");
      return;
    }

    profileMutation.mutate({
      name: name.trim(),
      title: title.trim(),
      email: email.trim(),
      phone: phone.trim(),
      location: location.trim(),
      portfolio: portfolio.trim(),
      github: github.trim(),
      linkedin: linkedin.trim(),
      languages_spoken: csv(languagesSpoken),
      interests: csv(interests),
      education: advanced.education ?? [],
      experience: advanced.experience ?? [],
      projects: advanced.projects ?? [],
      skills: {
        languages: csv(skillLangs),
        frameworks: csv(skillFrameworks),
        tools: csv(skillTools),
        databases: csv(skillDatabases),
        certifications: csv(skillCerts),
        coursework: csv(skillCoursework),
      },
      target_roles: csv(targetRoles),
      target_locations: csv(targetLocations),
    });
  };

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Setup Wizard</h1>
        <p className="page-subtitle">Step {step} of 3</p>
      </div>

      {step === 1 && (
        <div className="card" style={{ maxWidth: 560 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
            <Rocket size={22} color="var(--accent)" />
            <h2 style={{ fontSize: 20, fontWeight: 800 }}>Welcome to JobHunter AI</h2>
          </div>
          <p style={{ fontSize: 14, color: "var(--text2)", lineHeight: 1.7, marginBottom: 20 }}>
            JobHunter AI scans job boards for postings that match your profile, scores each one
            for fit using AI, and drafts a tailored CV and cover letter you can review and send.
            Let&apos;s get it configured — it only takes a minute.
          </p>
          <button className="btn btn-primary" onClick={() => setStep(2)}>
            Get Started <ChevronRight size={16} />
          </button>
        </div>
      )}

      {step === 2 && (
        <div className="card" style={{ maxWidth: 560 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 16 }}>API Keys</h2>
          <p style={{ fontSize: 13, color: "var(--text2)", marginBottom: 16 }}>
            All of these are optional — skip any of them and add them later from Settings.
          </p>

          <div style={{ marginBottom: 14 }}>
            <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 6, color: "var(--text2)" }}>
              Gemini API key
            </label>
            <div style={{ display: "flex", gap: 8 }}>
              <input
                className="input"
                type={showGemini ? "text" : "password"}
                value={geminiKey}
                onChange={e => setGeminiKey(e.target.value)}
                placeholder="AIza..."
              />
              <button type="button" className="btn btn-ghost" onClick={() => setShowGemini(v => !v)}>
                {showGemini ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
            <p style={{ fontSize: 12, color: "var(--text2)", marginTop: 6 }}>
              Powers AI job-fit scoring and CV/cover-letter writing. Free at{" "}
              <a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer">aistudio.google.com/apikey</a>.
              Skip this and jobs are still collected, but stay &quot;pending AI check&quot; — no fit scores or verdicts.
            </p>
          </div>

          <Field
            label="Groq API key"
            type="password"
            value={groqKey}
            onChange={e => setGroqKey(e.target.value)}
            placeholder="gsk_..."
            hint="Runs the high-volume job triage so Gemini's small free quota is saved for CVs and cover letters. Free at console.groq.com/keys. Either key alone works."
          />

          <Field
            label="OpenRouter API key (optional)"
            type="password"
            value={openrouterKey}
            onChange={e => setOpenrouterKey(e.target.value)}
            placeholder="sk-or-..."
            hint="Last-resort fallback when Groq and Gemini are out of quota. Free models at openrouter.ai/keys."
          />

          <Field
            label="RapidAPI key (JSearch)"
            value={rapidapiKey}
            onChange={e => setRapidapiKey(e.target.value)}
            placeholder="rapidapi key"
            hint="Pulls jobs from LinkedIn/Indeed/Glassdoor via JSearch (rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch, free tier 200 req/month). Skip this and you'll only get Tunisia listings from Keejob."
          />

          <Field
            label="Gmail address"
            value={gmailFrom}
            onChange={e => setGmailFrom(e.target.value)}
            placeholder="you@gmail.com"
          />
          <Field
            label="Gmail App Password"
            type="password"
            value={gmailPassword}
            onChange={e => setGmailPassword(e.target.value)}
            placeholder="xxxx xxxx xxxx xxxx"
            hint="Used to send your application emails. Create an App Password (not your real password) at support.google.com/accounts/answer/185833. Skip this and you can still generate CVs, just send them yourself."
          />

          <div style={{ display: "flex", gap: 10, marginTop: 8 }}>
            <button className="btn btn-ghost" onClick={() => setStep(1)}>
              <ChevronLeft size={16} /> Back
            </button>
            <button className="btn btn-ghost" onClick={() => setStep(3)}>
              Skip for now
            </button>
            <button className="btn btn-primary" onClick={handleSaveKeys} disabled={keysMutation.isPending}>
              Save & Continue <ChevronRight size={16} />
            </button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="card" style={{ maxWidth: 720 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 6 }}>Your Profile</h2>
          <p style={{ fontSize: 13, color: "var(--text2)", marginBottom: 16 }}>
            This is what every job gets scored against.
          </p>

          <div className="grid-2" style={{ gap: 12 }}>
            <Field label="Name" value={name} onChange={e => setName(e.target.value)} placeholder="Jane Doe" />
            <Field label="Title" value={title} onChange={e => setTitle(e.target.value)} placeholder="Software Engineer" />
            <Field label="Email" value={email} onChange={e => setEmail(e.target.value)} placeholder="jane@example.com" />
            <Field label="Phone" value={phone} onChange={e => setPhone(e.target.value)} placeholder="+1 555 000 0000" />
            <Field label="Location" value={location} onChange={e => setLocation(e.target.value)} placeholder="City, Country" />
            <Field label="Portfolio URL" value={portfolio} onChange={e => setPortfolio(e.target.value)} placeholder="https://..." />
            <Field label="GitHub URL" value={github} onChange={e => setGithub(e.target.value)} placeholder="https://github.com/..." />
            <Field label="LinkedIn URL" value={linkedin} onChange={e => setLinkedin(e.target.value)} placeholder="https://linkedin.com/in/..." />
            <Field label="Languages spoken (comma-separated)" value={languagesSpoken} onChange={e => setLanguagesSpoken(e.target.value)} placeholder="English, French" />
            <Field label="Interests (comma-separated)" value={interests} onChange={e => setInterests(e.target.value)} placeholder="Chess, Reading" />
          </div>

          <Field
            label="Target roles (comma-separated)"
            value={targetRoles}
            onChange={e => setTargetRoles(e.target.value)}
            placeholder="Software Engineer, Backend Developer"
            hint="Feeds the job scanner directly — these are the titles it searches for."
          />
          <Field
            label="Target locations (comma-separated)"
            value={targetLocations}
            onChange={e => setTargetLocations(e.target.value)}
            placeholder="Remote, Germany, Canada"
            hint="Feeds the job scanner directly — these are the locations it searches in."
          />

          <h3 style={{ fontSize: 15, fontWeight: 700, margin: "20px 0 10px" }}>Skills</h3>
          <div className="grid-2" style={{ gap: 12 }}>
            <Field label="Languages" value={skillLangs} onChange={e => setSkillLangs(e.target.value)} placeholder="Python, TypeScript" />
            <Field label="Frameworks" value={skillFrameworks} onChange={e => setSkillFrameworks(e.target.value)} placeholder="React, FastAPI" />
            <Field label="Tools" value={skillTools} onChange={e => setSkillTools(e.target.value)} placeholder="Git, Docker" />
            <Field label="Databases" value={skillDatabases} onChange={e => setSkillDatabases(e.target.value)} placeholder="PostgreSQL, MongoDB" />
            <Field label="Certifications" value={skillCerts} onChange={e => setSkillCerts(e.target.value)} placeholder="AWS SAA" />
            <Field label="Coursework" value={skillCoursework} onChange={e => setSkillCoursework(e.target.value)} placeholder="Data Structures" />
          </div>

          <button
            type="button"
            className="btn btn-ghost"
            style={{ marginTop: 8, marginBottom: 10 }}
            onClick={() => setShowAdvanced(v => !v)}
          >
            Advanced: education, experience, projects (JSON) {showAdvanced ? "▲" : "▼"}
          </button>
          {showAdvanced && (
            <textarea
              className="input"
              value={advancedJson}
              onChange={e => setAdvancedJson(e.target.value)}
              spellCheck={false}
              style={{ minHeight: 220, resize: "vertical", fontFamily: "monospace", fontSize: 13, lineHeight: 1.6 }}
            />
          )}

          <div style={{ display: "flex", gap: 10, marginTop: 20 }}>
            <button className="btn btn-ghost" onClick={() => setStep(2)}>
              <ChevronLeft size={16} /> Back
            </button>
            <button className="btn btn-primary" onClick={handleFinish} disabled={profileMutation.isPending}>
              Finish Setup
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
