import { useId, useState } from "react";
import type { InputHTMLAttributes } from "react";

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "aria-label"> & {
  /** Название поля: уходит в aria-label поля и в подпись кнопки «Показать». */
  label: string;
};

/** Поле пароля с кнопкой «Показать/Скрыть» — как на экране входа. */
export default function PasswordField({ label, id, ...rest }: Props) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const [visible, setVisible] = useState(false);

  return (
    <div className="password-field">
      <input {...rest} id={inputId} aria-label={label} type={visible ? "text" : "password"} />
      <button
        type="button"
        className="password-field__toggle"
        aria-controls={inputId}
        aria-label={`${visible ? "Скрыть" : "Показать"}: ${label.toLowerCase()}`}
        onClick={() => setVisible((v) => !v)}
      >
        {visible ? "Скрыть" : "Показать"}
      </button>
    </div>
  );
}
