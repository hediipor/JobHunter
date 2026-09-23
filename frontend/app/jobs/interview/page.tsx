"use client";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import api from "@/lib/api";
import { ArrowLeft, Loader2, MessagesSquare, ThumbsUp, ThumbsDown } from "lucide-react";
import toast from "react-hot-toast";

interface FeedbackItem { question_index: number; verdict: "strong" | "improve"; note: string }

function InterviewContent() {
  const id = useSearchParams().get("id");
  const [answers, setAnswers] = useState<string[]>([]);
  // Page state only — not persisted. If this turns out to be wanted, save
  // it to applications.notes instead of adding a table for it.
  const [feedback, setFeedback] = useState<FeedbackItem[] | null>(null);
  const [answerError, setAnswerError] = useState("");

  const { data, isLoading } = useQuery<{ questions: string[] }>({
    queryKey: ["interview", id],
    queryFn: () => api.post(`/jobs/${id}/interview`),
    enabled: !!id,
  });
  const questions = data?.questions ?? [];

  const feedbackMutation = useMutation({
    mutationFn: (qa: { question: string; answer: string }[]) =>
      api.post(`/jobs/${id}/interview/feedback`, { answers: qa }),
    onSuccess: (d: { feedback: FeedbackItem[] }) => setFeedback(d.feedback),
    onError: (e: Error) => toast.error(e.message),
  });

  const getFeedback = () => {
    const qa = questions
      .map((q, i) => ({ question: q, answer: (answers[i] || "").trim() }))
      .filter(a => a.answer);
    if (!qa.length) {
      setAnswerError("Answer at least one question first.");
      return;
    }
    setAnswerError("");
    feedbackMutation.mutate(qa);
  };

  const noteFor = (i: number) => feedback?.find(f => f.question_index === i);

  if (!id) return <div className="empty"><h3>Job not found</h3></div>;

  return (
    <div>
      <Link href={`/jobs/detail?id=${id}`} className="btn btn-ghost btn-sm" style={{ marginBottom: 20 }}>
        <ArrowLeft size={15} /> Back to Job
      </Link>

      <div className="page-header">
        <h1 className="page-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <MessagesSquare size={22} color="var(--accent2)" /> Practice Interview
        </h1>
        <p className="page-subtitle">5 questions tailored to this role — answer what you can, then get feedback.</p>
      </div>

      {isLoading ? <div className="spinner" /> : (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {questions.map((q, i) => {
            const note = noteFor(i);
            return (
              <div key={i} className="card">
                <p style={{ fontSize: 14, fontWeight: 700, marginBottom: 10 }}>{i + 1}. {q}</p>
                <textarea
                  className="input"
                  rows={4}
                  placeholder="Your answer (optional)"
                  value={answers[i] || ""}
                  onChange={e => setAnswers(a => { const next = [...a]; next[i] = e.target.value; return next; })}
                  style={{ resize: "vertical" }}
                />
                {note && (
                  <div style={{ display: "flex", gap: 8, alignItems: "flex-start", marginTop: 10,
                    fontSize: 13, color: note.verdict === "strong" ? "var(--green)" : "var(--yellow)" }}>
                    {note.verdict === "strong" ? <ThumbsUp size={15} style={{ marginTop: 1, flexShrink: 0 }} />
                      : <ThumbsDown size={15} style={{ marginTop: 1, flexShrink: 0 }} />}
                    <span>
                      <strong>{note.verdict === "strong" ? "Strong" : "Improve"}</strong> — {note.note}
                    </span>
                  </div>
                )}
              </div>
            );
          })}

          {questions.length > 0 && (
            <div>
              {answerError && (
                <p style={{ fontSize: 13, color: "var(--red)", marginBottom: 8 }}>{answerError}</p>
              )}
              <button className="btn btn-primary" onClick={getFeedback} disabled={feedbackMutation.isPending}>
                {feedbackMutation.isPending
                  ? <><Loader2 size={16} style={{ animation: "spin 0.7s linear infinite" }} /> Getting feedback…</>
                  : "Get Feedback"
                }
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function InterviewPage() {
  return (
    <Suspense fallback={<div className="spinner" />}>
      <InterviewContent />
    </Suspense>
  );
}
