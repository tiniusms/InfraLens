import {
  parseErrorResponse,
  parseEvaluationSummary,
  parseFinance,
  parseHistory,
  parseHoldout,
  parseHoldoutCases,
  parsePjmCatalog,
  parsePjmScreen,
  parseStatus,
} from "./parse";
import type {
  EvaluationSummary,
  FinanceRequest,
  FinanceResponse,
  HistoryResponse,
  HoldoutCasesResponse,
  HoldoutResponse,
  PjmCatalogResponse,
  PjmScreenResponse,
  StatusResponse,
} from "./types";

export type ClientFailureKind = "connection" | "http" | "invalid_body";

export class ApiClientError extends Error {
  readonly kind: ClientFailureKind;
  readonly status: number | null;
  readonly code: string | null;
  readonly field: string | null;

  constructor(
    kind: ClientFailureKind,
    message: string,
    status: number | null = null,
    code: string | null = null,
    field: string | null = null,
  ) {
    super(message);
    this.name = "ApiClientError";
    this.kind = kind;
    this.status = status;
    this.code = code;
    this.field = field;
  }
}

export type ApiClient = {
  getStatus: (signal?: AbortSignal) => Promise<StatusResponse>;
  getEvaluationSummary: (signal?: AbortSignal) => Promise<EvaluationSummary>;
  getHistory: (stateId: string, signal?: AbortSignal) => Promise<HistoryResponse>;
  getHoldout: (stateId: string, signal?: AbortSignal) => Promise<HoldoutResponse>;
  getHoldoutCases: (signal?: AbortSignal) => Promise<HoldoutCasesResponse>;
  postFinanceScenarios: (body: FinanceRequest, signal?: AbortSignal) => Promise<FinanceResponse>;
  getPjmCatalog: (signal?: AbortSignal) => Promise<PjmCatalogResponse>;
  getPjmScreen: (zone: string, forecastYear: number, asOf: string, signal?: AbortSignal) => Promise<PjmScreenResponse>;
};

/** Absolute API origin, or an empty string for same-origin `/api` requests.

An unset value keeps the local default. An explicit empty string is same-origin.
The public Vercel build sets an `https` origin instead. See `docs/portable_deployment.md`.
*/
export function resolveApiBaseUrl(configured: string | undefined): string {
  if (configured === undefined) {
    return "http://127.0.0.1:8000";
  }
  return configured.trim().replace(/\/$/, "");
}

function apiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL;
  if (typeof configured !== "string") {
    return resolveApiBaseUrl(undefined);
  }
  return resolveApiBaseUrl(configured);
}

async function requestJson<T>(
  fetchImpl: typeof fetch,
  baseUrl: string,
  path: string,
  parse: (value: unknown) => T,
  signal: AbortSignal | undefined,
  body?: unknown,
): Promise<T> {
  let response: Response;
  try {
    response = await fetchImpl(`${baseUrl}${path}`, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? { Accept: "application/json" } : { Accept: "application/json", "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (signal?.aborted) {
      throw error;
    }
    throw new ApiClientError("connection", "The InfraLens API did not respond.");
  }

  const text = await response.text();
  let payload: unknown = null;
  if (text !== "") {
    try {
      payload = JSON.parse(text) as unknown;
    } catch {
      throw new ApiClientError(
        "invalid_body",
        "The response was not JSON. Figures are not shown.",
        response.status,
      );
    }
  }

  if (!response.ok) {
    const parsed = parseErrorResponse(payload);
    throw new ApiClientError(
      "http",
      parsed?.message ?? "Request failed.",
      response.status,
      parsed?.code ?? null,
      parsed?.field ?? null,
    );
  }

  try {
    return parse(payload);
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
    getStatus: (signal) => requestJson(fetchImpl, baseUrl, "/api/v1/status", parseStatus, signal),
    getEvaluationSummary: (signal) =>
      requestJson(fetchImpl, baseUrl, "/api/v1/evaluation/summary", parseEvaluationSummary, signal),
    getHistory: (stateId, signal) =>
      requestJson(
        fetchImpl,
        baseUrl,
        `/api/v1/eia/history?state_id=${encodeURIComponent(stateId)}`,
        parseHistory,
        signal,
      ),
    getHoldout: (stateId, signal) =>
      requestJson(
        fetchImpl,
        baseUrl,
        `/api/v1/eia/holdout?state_id=${encodeURIComponent(stateId)}`,
        parseHoldout,
        signal,
      ),
    getHoldoutCases: (signal) =>
      requestJson(fetchImpl, baseUrl, "/api/v1/eia/holdout/cases", parseHoldoutCases, signal),
    postFinanceScenarios: (body, signal) =>
      requestJson(fetchImpl, baseUrl, "/api/v1/finance/scenarios", parseFinance, signal, body),
    getPjmCatalog: (signal) => requestJson(fetchImpl, baseUrl, "/api/v1/pjm/catalog", parsePjmCatalog, signal),
    getPjmScreen: (zone, forecastYear, asOf, signal) => {
      const params = new URLSearchParams({
        pjm_zone: zone,
        forecast_year: String(forecastYear),
        as_of: asOf,
      });
      return requestJson(fetchImpl, baseUrl, `/api/v1/pjm/screen?${params.toString()}`, parsePjmScreen, signal);
    },
  };
}

export const apiClient = createClient();
