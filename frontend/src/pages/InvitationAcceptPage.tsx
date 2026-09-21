import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";

interface InvitationPreview {
  full_name: string;
  role: string;
  groups: string[];
}

export default function InvitationAcceptPage() {
  const { token } = useParams<{ token: string }>();
  const [preview, setPreview] = useState<InvitationPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const { loginWithToken } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!token) return;
    api
      .get<InvitationPreview>(`/auth/invitations/${token}`)
      .then(setPreview)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Ссылка недействительна"));
  }, [token]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setError(null);
    setBusy(true);
    try {
      const res = await api.post<{ access_token: string }>(`/auth/invitations/${token}/accept`, { password });
      await loginWithToken(res.access_token);
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось создать пароль");
    } finally {
      setBusy(false);
    }
  }

  if (error && !preview) {
    return (
      <div className="auth-screen">
        <div className="auth-screen__visual">
          <div className="auth-screen__visual-content">
            <h2>КАИТ №20</h2>
            <p>Учёт посещаемости</p>
          </div>
        </div>
        <div className="auth-screen__form">
          <div className="auth-card">
            <img src="/kait20-logo.webp" alt="КАИТ №20" className="auth-card__logo" />
            <h1>Ссылка недействительна</h1>
            <p>{error}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-screen">
      <div className="auth-screen__visual">
        <div className="auth-screen__visual-content">
          <h2>Добро пожаловать в КАИТ-20</h2>
          <p>Осталось задать пароль — и личный кабинет готов к работе.</p>
        </div>
      </div>

      <div className="auth-screen__form">
        <form className="auth-card" onSubmit={handleSubmit}>
          <img src="/kait20-logo.webp" alt="КАИТ №20" className="auth-card__logo" />
          <h1>Добро пожаловать</h1>
          {preview && (
            <>
              <p className="subtitle">{preview.full_name}</p>
              {preview.groups.length > 0 && <p>Группы: {preview.groups.join(", ")}</p>}
            </>
          )}
          <label>
            Придумайте пароль
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={6} />
          </label>
          {error && <div className="error-text">{error}</div>}
          <button type="submit" disabled={busy || !preview}>
            {busy ? "Сохраняем…" : "Начать работу"}
          </button>
        </form>
      </div>
    </div>
  );
}
