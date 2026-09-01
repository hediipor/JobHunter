import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/Sidebar";
import { QueryProvider } from "@/components/QueryProvider";
import { Toaster } from "react-hot-toast";

export const metadata: Metadata = {
  title: "JobHunter AI — Hedi Bou Maiza",
  description: "Personal AI-powered job finder and application assistant",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <QueryProvider>
          <div className="layout">
            <Sidebar />
            <main className="main-content">{children}</main>
          </div>
          <Toaster
            position="bottom-right"
            toastOptions={{
              style: {
                background: "#13132a",
                color: "#f1f5f9",
                border: "1px solid rgba(255,255,255,0.08)",
              },
            }}
          />
        </QueryProvider>
      </body>
    </html>
  );
}
