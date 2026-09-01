"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, Briefcase, FileCheck2, User, Settings, Zap,
} from "lucide-react";
import styles from "./Sidebar.module.css";

const NAV = [
  { href: "/",              icon: LayoutDashboard, label: "Dashboard" },
  { href: "/jobs",          icon: Briefcase,        label: "Jobs" },
  { href: "/applications",  icon: FileCheck2,       label: "Applications" },
  { href: "/profile",       icon: User,             label: "Profile" },
  { href: "/settings",      icon: Settings,         label: "Settings" },
];

export default function Sidebar() {
  const path = usePathname();
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
        <div className={styles.avatar}>HB</div>
        <div>
          <div className={styles.avatarName}>Hedi Bou Maiza</div>
          <div className={styles.avatarRole}>Software Engineer</div>
        </div>
      </div>
    </aside>
  );
}
