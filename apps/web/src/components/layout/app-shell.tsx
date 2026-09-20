"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  FileText,
  GitCompareArrows,
  History,
  LayoutList,
  Network,
  Settings2,
} from "lucide-react";

import { PlatformStatus } from "@/components/layout/platform-status";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/mission-control", label: "Mission Control", icon: Activity },
  { href: "/scenarios", label: "Scenarios", icon: LayoutList },
  { href: "/runs", label: "Runs", icon: History },
  { href: "/compare", label: "Compare", icon: GitCompareArrows },
  { href: "/reports", label: "Reports", icon: FileText },
  { href: "/system", label: "System", icon: Network },
  { href: "/settings", label: "Settings", icon: Settings2 },
] as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 flex h-12 items-center gap-6 border-b border-border bg-elevated/95 px-4 backdrop-blur">
        <Link href="/mission-control" className="flex items-center gap-2.5" aria-label="Home">
          <span
            aria-hidden
            className="inline-flex h-6 w-6 items-center justify-center rounded-sm border border-info/50 bg-info-soft"
          >
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" className="text-info">
              <path d="M12 3v18M3 12h18" strokeWidth="1.6" />
              <circle cx="12" cy="12" r="4.5" strokeWidth="1.6" />
            </svg>
          </span>
          <span className="text-[12px] font-semibold tracking-[0.18em] text-foreground">
            RESILIENT UAS LAB
          </span>
        </Link>
        <nav aria-label="Primary" className="flex h-full items-stretch gap-1 overflow-x-auto">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || pathname.startsWith(`${href}/`);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "relative flex items-center gap-1.5 px-2.5 text-[12px] font-medium text-muted transition-colors hover:text-foreground",
                  active && "text-foreground",
                )}
              >
                <Icon size={14} aria-hidden />
                <span>{label}</span>
                {active && (
                  <span aria-hidden className="absolute inset-x-1.5 bottom-0 h-[2px] rounded-full bg-info" />
                )}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto flex items-center gap-4">
          <PlatformStatus />
        </div>
      </header>
      <main className="flex-1 min-w-[1024px]">{children}</main>
    </div>
  );
}
