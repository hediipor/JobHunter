"use client";
import { useState } from "react";
import { ThumbsUp, ThumbsDown, X } from "lucide-react";

const REASON_CHIPS = ["Too senior", "Wrong stack", "Location / visa", "Not interested in the company"];

interface Props {
  feedback?: number | null;
  onRate: (feedback: number, reason?: string) => void;
}

export default function FeedbackButtons({ feedback, onRate }: Props) {
  const [showReason, setShowReason] = useState(false);
  const [reason, setReason] = useState("");

  const thumbsUp = () => {
    setShowReason(false);
    onRate(feedback === 1 ? 0 : 1);
  };

  const thumbsDown = () => {
    if (feedback === -1) {
      setShowReason(false);
      onRate(0);
      return;
    }
    onRate(-1);
    setShowReason(true);
  };

  const pickReason = (r: string) => {
    onRate(-1, r || undefined);
    setShowReason(false);
    setReason("");
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", gap: 6 }}>
        <button type="button" className="btn btn-ghost btn-sm" onClick={thumbsUp}
          title={feedback === 1 ? "Remove rating" : "Good fit"}
          style={{ color: feedback === 1 ? "var(--green)" : undefined }}>
          <ThumbsUp size={14} fill={feedback === 1 ? "currentColor" : "none"} />
        </button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={thumbsDown}
          title={feedback === -1 ? "Remove rating" : "Not a fit"}
          style={{ color: feedback === -1 ? "var(--red)" : undefined }}>
          <ThumbsDown size={14} fill={feedback === -1 ? "currentColor" : "none"} />
        </button>
      </div>
      {showReason && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
            {REASON_CHIPS.map(c => (
              <button key={c} type="button" className="badge badge-source"
                style={{ cursor: "pointer", background: "none" }} onClick={() => pickReason(c)}>
                {c}
              </button>
            ))}
            <button type="button" className="btn btn-ghost btn-sm" style={{ padding: 4 }}
              title="Dismiss" onClick={() => setShowReason(false)}>
              <X size={12} />
            </button>
          </div>
          <input
            className="input"
            placeholder="Other reason (optional, press Enter)"
            value={reason}
            onChange={e => setReason(e.target.value)}
            onKeyDown={e => e.key === "Enter" && pickReason(reason.trim())}
            style={{ fontSize: 12, padding: "6px 8px" }}
          />
        </div>
      )}
    </div>
  );
}
