"use client";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import api from "@/lib/api";

interface SetupStatus {
  setup_complete: boolean;
}

// next.config.ts sets trailingSlash: true (required for the static export to
// serve nested routes), so usePathname() returns "/setup/" once client-side
// navigation lands here — not the bare "/setup" this used to compare against,
// which caused an infinite fetch/redirect loop that never rendered anything.
const isSetupPath = (p: string | null) => (p ?? "").replace(/\/$/, "") === "/setup";

export default function SetupGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(isSetupPath(pathname));

  const { data, isFetched } = useQuery<SetupStatus>({
    queryKey: ["setup-status"],
    queryFn: () => api.get("/setup/status"),
    enabled: !isSetupPath(pathname),
  });

  useEffect(() => {
    if (isSetupPath(pathname)) {
      setReady(true);
      return;
    }
    if (!isFetched) return;
    if (!data?.setup_complete) {
      router.replace("/setup");
      return;
    }
    setReady(true);
  }, [pathname, isFetched, data, router]);

  if (!ready) return null;
  return <>{children}</>;
}
