import { createContext } from "react";
import type { MeResponse } from "../api/types";

export interface AuthContextValue {
  user: MeResponse | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  loginWithToken: (token: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);
