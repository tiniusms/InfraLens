import type { ReactNode } from "react";
import { ApiContext } from "./api-context";
import { apiClient, type ApiClient } from "./client";

export function ApiProvider({ client = apiClient, children }: { client?: ApiClient; children: ReactNode }) {
  return <ApiContext.Provider value={client}>{children}</ApiContext.Provider>;
}
