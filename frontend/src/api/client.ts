import type { ApiErrorBody } from '../types';

export const API_BASE: string =
  (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000';

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly recoverable: boolean;

  constructor(status: number, code: string, message: string, recoverable: boolean) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.recoverable = recoverable;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers: { 'Content-Type': 'application/json', ...init?.headers },
      ...init,
    });
  } catch {
    throw new ApiError(0, 'network_error', 'Could not reach the backend', true);
  }

  if (!res.ok) {
    let body: ApiErrorBody | undefined;
    try {
      body = (await res.json()) as ApiErrorBody;
    } catch {
      // non-JSON error body; fall through to generic error
    }
    throw new ApiError(
      res.status,
      body?.error?.code ?? `http_${res.status}`,
      body?.error?.message ?? `Request failed (${res.status})`,
      body?.error?.recoverable ?? false,
    );
  }

  // 202/204 with an empty body are valid for cancel.
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export const http = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) }),
};
