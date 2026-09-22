import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import type { MeResponse } from "../api/types";

export default function ChangePasswordPage() {
  const { user, refresh } = useAuth();
  const navigate = useNavigate();
  const forced = user?.must_change_password ?? false;

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (newPassword !== confirmPassword) {
      setError("Пароли не совпадают");
      return;
    }
    setBusy(true);
    try {
      await api.post<MeResponse>("/auth/change-password", {
        current_password: forced ? undefined : currentPassword,
        new_password: newPassword,
      });
      await refresh();
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сменить пароль");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-screen">
      <div className="auth-screen__visual">
        <div className="auth-screen__visual-content">
          <h2>{forced ? "Пора задать свой пароль" : "Смена пароля"}</h2>
          <p>
            {forced
              ? "Администратор выдал временный пароль — прежде чем продолжить, задайте собственный."
              : "Введите текущий пароль и новый, который будете использовать дальше."}
          </p>
        </div>
      </div>

      <div className="auth-screen__form">
        <form className="auth-card" onSubmit={handleSubmit}>
          <img src="/kait20-logo.webp" alt="КАИТ №20" className="auth-card__logo" />
          <h1>{forced ? "Новый пароль" : "Смена пароля"}</h1>
          {user && <p className="subtitle">{user.full_name}</p>}

          {!forced && (
            <label>
              Текущий пароль
              <input
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                autoFocus
                required
              />
            </label>
          )}

          <label>
            Новый пароль
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              autoFocus={forced}
              required
              minLength={8}
            />
          </label>

          <label>
            Повторите новый пароль
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              minLength={8}
            />
          </label>

          {error && <div className="error-text">{error}</div>}

          <button type="submit" disabled={busy}>
            {busy ? "Сохраняем…" : "Сохранить пароль"}
          </button>

          {!forced && (
            <button type="button" className="link-btn" onClick={() => navigate(-1)}>
              Отмена
            </button>
          )}
        </form>
      </div>
    </div>
  );
}
