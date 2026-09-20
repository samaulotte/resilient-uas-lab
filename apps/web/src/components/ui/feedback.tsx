"use client";

import { AlertTriangle, Inbox, Loader2, PlugZap } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ApiError, describeError } from "@/lib/api";
import { cn } from "@/lib/utils";

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div aria-hidden className={cn("animate-pulse rounded-sm bg-panel-2", className)} {...props} />
  );
}

export function SkeletonRows({ rows = 5, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)} role="status" aria-label="Loading">
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} className="h-6 w-full" style={{ opacity: 1 - index * 0.12 }} />
      ))}
    </div>
  );
}

export function LoadingPanel({
  label = "Loading",
  className,
}: {
  label?: string;
  className?: string;
}) {
  return (
    <div
      role="status"
      className={cn("flex items-center gap-2 p-4 text-[12px] text-muted", className)}
    >
      <Loader2 size={13} className="animate-spin" aria-hidden />
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  icon: Icon = Inbox,
  action,
  className,
}: {
  title: string;
  description?: React.ReactNode;
  icon?: React.ComponentType<{ size?: number; className?: string }>;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 px-6 py-10 text-center",
        className,
      )}
    >
      <Icon size={22} className="text-dim" aria-hidden />
      <p className="text-[13px] font-medium text-foreground">{title}</p>
      {description ? (
        <p className="max-w-[46ch] text-[12px] leading-snug text-muted">{description}</p>
      ) : null}
      {action ? <div className="mt-1">{action}</div> : null}
    </div>
  );
}

/** Human readable message for any thrown value, never a stack trace. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 0) return "The API is not reachable from this browser.";
    return describeError(error.detail, error.status);
  }
  if (error instanceof TypeError) return "The API is not reachable from this browser.";
  if (error instanceof Error) return error.message;
  return "Unexpected error.";
}

export function ErrorState({
  title = "Request failed",
  error,
  onRetry,
  className,
}: {
  title?: string;
  error: unknown;
  onRetry?: () => void;
  className?: string;
}) {
  const unreachable =
    error instanceof TypeError || (error instanceof ApiError && error.status === 0);
  const Icon = unreachable ? PlugZap : AlertTriangle;
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center justify-center gap-2 px-6 py-10 text-center",
        className,
      )}
    >
      <Icon size={22} className="text-bad" aria-hidden />
      <p className="text-[13px] font-medium text-foreground">{title}</p>
      <p className="max-w-[52ch] text-[12px] leading-snug text-muted">{errorMessage(error)}</p>
      {onRetry ? (
        <Button className="mt-1" onClick={onRetry} variant="outline">
          Retry
        </Button>
      ) : null}
    </div>
  );
}

export function InlineError({ message, className }: { message: string; className?: string }) {
  return (
    <p
      role="alert"
      className={cn(
        "flex items-start gap-1.5 rounded-sm border border-bad/40 bg-bad-soft px-2 py-1.5 text-[11.5px] leading-snug text-bad",
        className,
      )}
    >
      <AlertTriangle size={12} className="mt-[1px] shrink-0" aria-hidden />
      <span>{message}</span>
    </p>
  );
}

export function Notice({
  tone = "info",
  children,
  className,
}: {
  tone?: "info" | "warn" | "bad" | "ok";
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <p
      className={cn(
        "rounded-sm border px-2.5 py-1.5 text-[11.5px] leading-snug",
        tone === "info" && "border-info/40 bg-info-soft text-info",
        tone === "warn" && "border-warn/40 bg-warn-soft text-warn",
        tone === "bad" && "border-bad/40 bg-bad-soft text-bad",
        tone === "ok" && "border-ok/40 bg-ok-soft text-ok",
        className,
      )}
    >
      {children}
    </p>
  );
}
