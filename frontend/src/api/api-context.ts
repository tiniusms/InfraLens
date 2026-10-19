import { createContext } from "react";
import { apiClient, type ApiClient } from "./client";

export const ApiContext = createContext<ApiClient>(apiClient);
