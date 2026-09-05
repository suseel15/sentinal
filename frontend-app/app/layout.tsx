import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/Sidebar";
import Topbar from "@/components/Topbar";

export const metadata: Metadata = {
  title: "SENTINEL — Investigation Command Center",
  description: "SENTINEL Financial Crime Investigation Platform — Investigator Dashboard"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen flex">
          <Sidebar />
          <div className="flex-1 flex flex-col min-w-0">
            <Topbar />
            <main className="flex-1 p-5 overflow-x-hidden">{children}</main>
          </div>
        </div>
      </body>
    </html>
  );
}