"use client";
import { Stats } from "@/lib/types";
import { LucideIcon } from "lucide-react";

interface Props {
  label: string;
  value: number | string;
  icon: LucideIcon;
  color?: string;
  suffix?: string;
}

export default function StatsCard({ label, value, icon: Icon, color = "var(--accent)", suffix = "" }: Props) {
  return (
    <div className="card" style={{ display: "flex", alignItems: "center", gap: 18 }}>
      <div style={{
        width: 48, height: 48, borderRadius: 12, flexShrink: 0,
        background: `${color}22`, border: `1px solid ${color}44`,
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        <Icon size={22} color={color} />
      </div>
      <div>
        <div style={{ fontSize: 26, fontWeight: 800, color: "var(--text)", lineHeight: 1 }}>
          {value}{suffix}
        </div>
        <div style={{ fontSize: 13, color: "var(--text2)", marginTop: 4 }}>{label}</div>
      </div>
    </div>
  );
}
