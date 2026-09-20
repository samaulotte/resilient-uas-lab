import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** Format simulation seconds as `T+MM:SS`. */
export function formatMissionTime(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return "T+--:--";
  const sign = seconds < 0 ? "-" : "+";
  const total = Math.floor(Math.abs(seconds));
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  return `T${sign}${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

/** Format a duration in seconds compactly (`250ms`, `4.2s`, `1m05s`). */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return "n/a";
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 60) return `${seconds.toFixed(1).replace(/\.0$/, "")}s`;
  const minutes = Math.floor(seconds / 60);
  const rem = Math.round(seconds - minutes * 60);
  return `${minutes}m${String(rem).padStart(2, "0")}s`;
}

export function formatPercent(ratio: number | null | undefined, digits = 1): string {
  if (ratio === null || ratio === undefined || Number.isNaN(ratio)) return "n/a";
  return `${(ratio * 100).toFixed(digits)}%`;
}

export function formatNumber(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return value.toFixed(digits);
}

export function shortId(id: string): string {
  return id.slice(0, 8);
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "n/a";
  const date = new Date(iso);
  return date.toISOString().replace("T", " ").slice(0, 19) + " UTC";
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "n/a";
  const delta = Math.max(0, Date.now() - new Date(iso).getTime());
  const seconds = Math.floor(delta / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}
