import { createContext } from "react";
import type { MeResponse } from "../api/types";

export interface AuthContextValue {
  user: MeResponse | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  /** Выйти только в этом браузере. */
  logout: () => void;
  /** Выйти на всех устройствах: сервер отзывает все сессии пользователя. */
  logoutAll: () => Promise<void>;
  refresh: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);
