/**
 * Duration strings used by the scenario schema (`30s`, `1m30s`, `250ms`).
 *
 * Mirrors `reslab_core.duration`: a bare number is never a valid duration, the unit
 * is always explicit so a value can never be misread as seconds or milliseconds.
 */

const DURATION_RE = /^(?:(\d+)h)?(?:(\d+)m(?!s))?(?:(\d+(?:\.\d+)?)s)?(?:(\d+)ms)?$/;

/** Parse a duration string into seconds; `null` when the string is not a duration. */
export function parseDuration(value: string): number | null {
  const text = value.trim();
  if (!text) return null;
  const match = DURATION_RE.exec(text);
  if (!match) return null;
  const [, hours, minutes, seconds, millis] = match;
  if (!hours && !minutes && !seconds && !millis) return null;
  return (
    Number(hours ?? 0) * 3600 +
    Number(minutes ?? 0) * 60 +
    Number(seconds ?? 0) +
    Number(millis ?? 0) / 1000
  );
}

export function isDuration(value: string): boolean {
  return parseDuration(value) !== null;
}

/** Format seconds as a canonical duration string accepted by the scenario schema. */
export function toDurationString(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0s";
  if (seconds > 0 && seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  const whole = Math.round(seconds * 10) / 10;
  if (whole < 60) return `${Number(whole.toFixed(1))}s`;
  const minutes = Math.floor(whole / 60);
  const rest = Math.round(whole - minutes * 60);
  if (rest === 0) return `${minutes}m`;
  return `${minutes}m${rest}s`;
}
