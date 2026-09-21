import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { ApiError } from "../api/client";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(username, password);
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось войти");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-screen">
      <div className="auth-screen__visual">
        <div className="auth-screen__visual-content">
          <h2>Учёт посещаемости без бумажных таблиц</h2>
          <p>Куратор отмечает исключения за полминуты — проценты, витрины и напоминания считает платформа.</p>
        </div>
      </div>

      <div className="auth-screen__form">
        <form className="auth-card" onSubmit={handleSubmit}>
          <img src="/kait20-logo.webp" alt="КАИТ №20" className="auth-card__logo" />
          <h1>Вход в платформу</h1>
          <p className="subtitle">Учёт посещаемости</p>

          <label>
            Логин
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus required />
          </label>

          <label>
            Пароль
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </label>

          {error && <div className="error-text">{error}</div>}

          <button type="submit" disabled={busy}>
            {busy ? "Входим…" : "Войти"}
          </button>
        </form>
      </div>
    </div>
  );
}
