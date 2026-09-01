"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, useEffect } from "react";
import api from "@/lib/api";
import { Save, User, Code, AlertCircle } from "lucide-react";
import toast from "react-hot-toast";

export default function ProfilePage() {
  const qc = useQueryClient();
  const [jsonText, setJsonText] = useState("");
  const [error, setError] = useState("");

  const { data: profile, isLoading } = useQuery({
    queryKey: ["profile"],
    queryFn: () => api.get("/profile/"),
  });

  useEffect(() => {
    if (profile && !jsonText) {
      setJsonText(JSON.stringify(profile, null, 2));
    }
  }, [profile, jsonText]);

  const saveMutation = useMutation({
    mutationFn: (data: any) => api.put("/profile/", data),
    onSuccess: () => {
      toast.success("Profile updated successfully!");
      qc.invalidateQueries({ queryKey: ["profile"] });
      setError("");
    },
    onError: () => toast.error("Failed to save profile. Ensure backend is running."),
  });

  const handleSave = () => {
    try {
      const parsed = JSON.parse(jsonText);
      saveMutation.mutate(parsed);
    } catch (e: any) {
      setError(`Invalid JSON: ${e.message}`);
      toast.error("Invalid JSON format. Check your syntax.");
    }
  };

  if (isLoading) return <div className="spinner" />;

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h1 className="page-title">Candidate Profile</h1>
          <p className="page-subtitle">Edit your raw JSON profile used for AI matching and document generation</p>
        </div>
        <button 
          className="btn btn-primary" 
          onClick={handleSave}
          disabled={saveMutation.isPending || jsonText === JSON.stringify(profile, null, 2)}
        >
          <Save size={16} /> Save Profile
        </button>
      </div>

      <div className="card" style={{ flex: 1, display: "flex", flexDirection: "column", padding: "20px" }}>
        <div style={{ display: "flex", gap: 16, marginBottom: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--text2)", fontSize: 14 }}>
            <Code size={16} /> JSON Editor
          </div>
          {error && (
            <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--red)", fontSize: 13 }}>
              <AlertCircle size={14} /> {error}
            </div>
          )}
        </div>
        <textarea
          value={jsonText}
          onChange={(e) => {
            setJsonText(e.target.value);
            setError("");
          }}
          style={{
            flex: 1,
            width: "100%",
            background: "var(--bg)",
            border: "1px solid var(--glass-border)",
            borderRadius: "var(--radius-sm)",
            color: "var(--text)",
            fontFamily: "monospace",
            fontSize: 13,
            padding: 16,
            resize: "none",
            outline: "none",
            minHeight: "500px"
          }}
          spellCheck="false"
        />
      </div>
    </div>
  );
}
