import { useContext } from "react";
import { AuthContext } from "./authContextObject";

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth должен использоваться внутри AuthProvider");
  return ctx;
}
