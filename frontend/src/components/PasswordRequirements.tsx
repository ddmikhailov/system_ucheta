import { PASSWORD_EXTRA_HINT, passwordRules } from "../constants/password";

// Чек-лист требований к паролю: отмечает выполненные по мере ввода.
export default function PasswordRequirements({ password }: { password: string }) {
  return (
    <div className="password-rules" aria-live="polite">
      <ul>
        {passwordRules(password).map((r) => (
          <li key={r.label} className={r.ok ? "password-rules__ok" : undefined}>
            <span aria-hidden="true">{r.ok ? "✓" : "•"}</span> {r.label}
            {r.ok && <span className="visually-hidden"> — выполнено</span>}
          </li>
        ))}
      </ul>
      <p>{PASSWORD_EXTRA_HINT}</p>
    </div>
  );
}
