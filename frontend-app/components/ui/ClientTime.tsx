"use client";
import { useEffect, useState } from "react";
import { fmtDate } from "@/lib/utils";

/** Hydration-safe timestamp: renders a stable placeholder on the server and
 *  during hydration, then the real formatted time only on the client.
 *  Use for any value that can differ between server render and client
 *  (demo/relative times, Date.now() fallbacks, differing timezones). */
export default function ClientTime({
  value,
  className,
}: {
  value?: string | null;
  className?: string;
}) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) {
    return (
      <span className={className} suppressHydrationWarning>
        —
      </span>
    );
  }
  return <span className={className}>{fmtDate(value)}</span>;
}
