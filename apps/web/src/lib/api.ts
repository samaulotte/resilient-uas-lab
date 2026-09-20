import { createApiClient, runStreamUrl } from "@reslab/api-client";

/**
 * Base URL of the API. Empty in production (same origin through the gateway); set to
 * `http://localhost:8000` in development via NEXT_PUBLIC_API_BASE.
 */
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

export const api = createApiClient({ baseUrl: API_BASE });

export function streamUrl(runId: string): string {
  return runStreamUrl(runId, API_BASE);
}

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface FetchResult<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

/** Unwrap an openapi-fetch result, turning API errors into `ApiError`. */
export async function unwrap<T>(promise: Promise<FetchResult<T>>): Promise<T> {
  const { data, error, response } = await promise;
  if (data === undefined) {
    throw new ApiError(describeError(error, response.status), response.status, error);
  }
  return data;
}

/** Convert an openapi-fetch error payload into a readable message. */
export function describeError(error: unknown, status?: number): string {
  if (error && typeof error === "object") {
    const record = error as Record<string, unknown>;
    if (typeof record.detail === "string") return record.detail;
    if (record.detail && typeof record.detail === "object") {
      const detail = record.detail as Record<string, unknown>;
      if (Array.isArray(detail.issues)) {
        return detail.issues
          .map((issue) => {
            const item = issue as Record<string, unknown>;
            return `${item.path ?? "$"}: ${item.message ?? "invalid"}`;
          })
          .join("; ");
      }
      if (typeof detail.error === "string") return detail.error;
    }
    if (typeof record.error === "string") return record.error;
  }
  if (error instanceof Error) return error.message;
  return status ? `request failed (${status})` : "request failed";
}
