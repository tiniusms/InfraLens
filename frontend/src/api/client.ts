import { parseErrorResponse, parseEvaluationSummary, parseStatus } from "./parse";
import type { EvaluationSummary, StatusResponse } from "./types";

export type ClientFailureKind = "connection" | "http" | "invalid_body";

export class ApiClientError extends Error {
  readonly kind: ClientFailureKind;
  readonly status: number | null;
  readonly code: string | null;

  constructor(kind: ClientFailureKind, message: string, status: number | null = null, code: string | null = null) {
    super(message);
    this.name = "ApiClientError";
    this.kind = kind;
    this.status = status;
    this.code = code;
  }
}

export type ApiClient = {
  getStatus: (signal?: AbortSignal) => Promise<StatusResponse>;
  getEvaluationSummary: (signal?: AbortSignal) => Promise<EvaluationSummary>;
};

function apiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL;
  if (typeof configured === "string" && configured.trim() !== "") {
    return configured.trim().replace(/\/$/, "");
  }
  return "http://127.0.0.1:8000";
}

async function getJson<T>(
  fetchImpl: typeof fetch,
  baseUrl: string,
  path: string,
  parse: (value: unknown) => T,
  signal?: AbortSignal,
): Promise<T> {
  let response: Response;
  try {
    response = await fetchImpl(`${baseUrl}${path}`, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal,
    });
  } catch (error) {
    if (signal?.aborted) {
      throw error;
    }
    throw new ApiClientError("connection", "The InfraLens API did not respond.");
  }

  const text = await response.text();
  let body: unknown = null;
  if (text !== "") {
    try {
      body = JSON.parse(text) as unknown;
    } catch {
      throw new ApiClientError(
        "invalid_body",
        "The response was not JSON. Figures are not shown.",
        response.status,
      );
    }
  }

  if (!response.ok) {
    const parsed = parseErrorResponse(body);
    throw new ApiClientError(
      "http",
      parsed?.message ?? "Request failed.",
      response.status,
      parsed?.code ?? null,
    );
  }

  try {
    return parse(body);
  } catch {
    throw new ApiClientError(
      "invalid_body",
      "The response did not match the API contract. Figures are not shown.",
      response.status,
    );
  }
}

export function createClient(options?: { baseUrl?: string; fetchImpl?: typeof fetch }): ApiClient {
  const fetchImpl = options?.fetchImpl ?? fetch;
  const baseUrl = (options?.baseUrl ?? apiBaseUrl()).replace(/\/$/, "");
  return {
    getStatus: (signal) => getJson(fetchImpl, baseUrl, "/api/v1/status", parseStatus, signal),
    getEvaluationSummary: (signal) =>
      getJson(fetchImpl, baseUrl, "/api/v1/evaluation/summary", parseEvaluationSummary, signal),
  };
}

export const apiClient = createClient();
