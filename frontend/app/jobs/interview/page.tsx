"use client";
import { useMutation } from "@tanstack/react-query";
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
  // Original question indexes of the answers actually sent, in sent order —
  // question_index in `feedback` refers to position in this list, not in `questions`.
  const [sentIndexes, setSentIndexes] = useState<number[]>([]);
  const [answerError, setAnswerError] = useState("");

  // Generating questions costs an LLM call, so it only runs on an explicit click.
  const [questions, setQuestions] = useState<string[]>([]);
  const startMutation = useMutation({
    mutationFn: () => api.post(`/jobs/${id}/interview`),
    onSuccess: (d: { questions: string[] }) => setQuestions(d.questions),
    onError: (e: Error) => toast.error(e.message),
  });

  const feedbackMutation = useMutation({
    mutationFn: (qa: { question: string; answer: string }[]) =>
      api.post(`/jobs/${id}/interview/feedback`, { answers: qa }),
    onSuccess: (d: { feedback: FeedbackItem[] }) => setFeedback(d.feedback),
    onError: (e: Error) => toast.error(e.message),
  });

  const getFeedback = () => {
    const qa = questions
      .map((q, i) => ({ i, question: q, answer: (answers[i] || "").trim() }))
      .filter(a => a.answer);
    if (!qa.length) {
      setAnswerError("Answer at least one question first.");
      return;
    }
    setAnswerError("");
    setFeedback(null);
    setSentIndexes(qa.map(a => a.i));
    feedbackMutation.mutate(qa.map(({ question, answer }) => ({ question, answer })));
  };

  const noteFor = (i: number) => {
    const sentPos = sentIndexes.indexOf(i);
    if (sentPos === -1) return undefined;
    return feedback?.find(f => f.question_index === sentPos);
  };

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

      {startMutation.isPending ? <div className="spinner" /> : !questions.length ? (
        <button className="btn btn-primary" onClick={() => startMutation.mutate()}>
          Start practice interview
        </button>
      ) : (
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
