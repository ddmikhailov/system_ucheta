import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { MIN_PASSWORD_LENGTH, passwordRulesMet } from "../constants/password";
import PasswordField from "../components/PasswordField";
import PasswordRequirements from "../components/PasswordRequirements";
import type { MeResponse } from "../api/types";
import { CollegeLogo } from "../components/BrandMark";

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
    if (!passwordRulesMet(newPassword)) {
      setError("Новый пароль не выполняет требования ниже");
      return;
    }
    setBusy(true);
    try {
      await api.post<MeResponse>("/auth/change-password", {
        current_password: forced ? undefined : currentPassword,
        new_password: newPassword,
      });
      // Смена пароля отзывает все ранее выданные токены (см. TODO.md 2), включая
      // текущий — сервер сразу ставит новую cookie сессии в этом же ответе.
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
              ? "Текущий пароль временный или не соответствует требованиям безопасности — прежде чем продолжить, задайте новый."
              : "Введите текущий пароль и новый, который будете использовать дальше."}
          </p>
        </div>
      </div>

      <div className="auth-screen__form">
        <form className="auth-card" onSubmit={handleSubmit}>
          <CollegeLogo className="auth-card__logo" />
          <h1>{forced ? "Новый пароль" : "Смена пароля"}</h1>
          {user && <p className="subtitle">{user.full_name}</p>}

          {!forced && (
            <label>
              Текущий пароль
              <PasswordField
                label="Текущий пароль"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                autoFocus
                required
              />
            </label>
          )}

          <label>
            Новый пароль
            <PasswordField
              label="Новый пароль"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              autoFocus={forced}
              required
              minLength={MIN_PASSWORD_LENGTH}
              autoComplete="new-password"
            />
          </label>

          <PasswordRequirements password={newPassword} />

          <label>
            Повторите новый пароль
            <PasswordField
              label="Повторите новый пароль"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              minLength={MIN_PASSWORD_LENGTH}
              autoComplete="new-password"
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
