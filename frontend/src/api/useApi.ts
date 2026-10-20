import { useContext } from "react";
import { ApiContext } from "./api-context";
import type { ApiClient } from "./client";

export function useApi(): ApiClient {
  return useContext(ApiContext);
}
