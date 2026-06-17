/**
 * Thin, typed API client.
 *
 * Centralizes the base URL, JSON handling, and error normalization so hooks and
 * components never touch `fetch` directly. Backend errors come back as
 * `{ error: { code, message } }`; we surface `message` as a thrown `ApiError`.
 */

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

export const API_URL = `${API_BASE}/api`;

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
}

// Free hosting tiers (e.g. Render) spin the backend down when idle; the first
// request then fails or returns a 502/503 for ~50s while it wakes up. These
// failures happen BEFORE the request reaches the app, so retrying them is safe
// (no double-execution) and lets the first action after idle succeed instead of
// showing an error. Delays sum to ~55s to cover a cold start.
const COLD_START_DELAYS_MS = [2000, 4000, 8000, 16000, 25000];
const RETRYABLE_STATUS = new Set([502, 503]);
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, signal } = options;

  for (let attempt = 0; ; attempt++) {
    let response: Response;
    try {
      response = await fetch(`${API_URL}${path}`, {
        method,
        signal,
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch {
      // Network error (incl. connection refused while the server boots).
      if (attempt < COLD_START_DELAYS_MS.length) {
        await sleep(COLD_START_DELAYS_MS[attempt]);
        continue;
      }
      throw new ApiError(
        "Could not reach the API. The server may be waking up — try again in a moment.",
        0,
        "network_error",
      );
    }

    // Gateway errors during cold start — the app hasn't received the request
    // yet, so retry rather than surface a failure.
    if (RETRYABLE_STATUS.has(response.status) && attempt < COLD_START_DELAYS_MS.length) {
      await sleep(COLD_START_DELAYS_MS[attempt]);
      continue;
    }

    if (response.status === 204) {
      return undefined as T;
    }

    const data = await response.json().catch(() => null);

    if (!response.ok) {
      const message = data?.error?.message ?? data?.detail ?? "Request failed.";
      throw new ApiError(message, response.status, data?.error?.code);
    }

    return data as T;
  }
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => request<T>(path, { signal }),
  post: <T>(path: string, body?: unknown, signal?: AbortSignal) =>
    request<T>(path, { method: "POST", body, signal }),
};
