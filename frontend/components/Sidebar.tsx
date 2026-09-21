"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, Briefcase, FileCheck2, User, Settings, Zap, Wand2,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import api from "@/lib/api";
import styles from "./Sidebar.module.css";

const NAV = [
  { href: "/",              icon: LayoutDashboard, label: "Dashboard" },
  { href: "/jobs",          icon: Briefcase,        label: "Jobs" },
  { href: "/applications",  icon: FileCheck2,       label: "Applications" },
  { href: "/profile",       icon: User,             label: "Profile" },
  { href: "/settings",      icon: Settings,         label: "Settings" },
  { href: "/setup",         icon: Wand2,            label: "Setup Wizard" },
];

export default function Sidebar() {
  const path = usePathname();
  // Shares the profile page's query. Before setup there's no profile (404) — don't retry.
  const { data: profile } = useQuery({ queryKey: ["profile"], queryFn: () => api.get("/profile/"), retry: false });
  return (
    <aside className={styles.sidebar}>
      <div className={styles.logo}>
        <Zap size={22} className={styles.logoIcon} />
        <span>JobHunter <b>AI</b></span>
      </div>

      <nav className={styles.nav}>
        {NAV.map(({ href, icon: Icon, label }) => {
          const active = href === "/" ? path === "/" : path.startsWith(href);
          return (
            <Link key={href} href={href} className={`${styles.link} ${active ? styles.active : ""}`}>
              <Icon size={18} />
              <span>{label}</span>
              {active && <span className={styles.activeDot} />}
            </Link>
          );
        })}
      </nav>

      <div className={styles.footer}>
        <div className={styles.avatar}>
          {(profile?.name || "?").split(/\s+/).map((w: string) => w[0]).slice(0, 2).join("").toUpperCase()}
        </div>
        <div>
          <div className={styles.avatarName}>{profile?.name || "Set up your profile"}</div>
          <div className={styles.avatarRole}>{profile?.title || ""}</div>
        </div>
      </div>
    </aside>
  );
}
