import { useImperativeHandle, useLayoutEffect, useRef, useState } from "react";
import type { Ref, TextareaHTMLAttributes } from "react";
import { useEscapeKey } from "../hooks/useEscapeKey";

// Сколько поле может вырасти само (дальше — прокрутка внутри или «развернуть на весь экран»).
const MAX_HEIGHT = 280;

type Props = TextareaHTMLAttributes<HTMLTextAreaElement> & {
  /** Заголовок окна «на весь экран» — обычно подпись поля. */
  expandTitle?: string;
  /** Ссылка на само поле — например, чтобы вернуть в него фокус при ошибке. */
  inputRef?: Ref<HTMLTextAreaElement>;
};

/** Многострочное поле: растягивать мышью нельзя (поле не «уезжает» за край), оно само растёт по тексту
 * до разумной высоты, а для длинного текста есть кнопка «Развернуть на весь экран». */
export default function TextArea({ expandTitle, className, value, onChange, disabled, inputRef, ...rest }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useImperativeHandle(inputRef, () => ref.current as HTMLTextAreaElement);
  const [expanded, setExpanded] = useState(false);

  // Высота по содержимому: сбросить и взять scrollHeight, но не выше MAX_HEIGHT.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    const next = Math.min(el.scrollHeight + 2, MAX_HEIGHT);
    if (next > 0) el.style.height = `${next}px`;
  }, [value]);

  return (
    <span className="textarea-wrap">
      <textarea
        ref={ref}
        className={`textarea-auto${className ? ` ${className}` : ""}`}
        value={value}
        onChange={onChange}
        disabled={disabled}
        {...rest}
      />
      {!disabled && (
        <button
          type="button"
          className="textarea-wrap__expand"
          aria-label="Развернуть на весь экран"
          title="Развернуть на весь экран"
          onClick={() => setExpanded(true)}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
            <path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      )}
      {expanded && (
        <FullscreenEditor
          title={expandTitle ?? "Текст"}
          value={typeof value === "string" ? value : String(value ?? "")}
          onChange={onChange}
          maxLength={rest.maxLength}
          placeholder={rest.placeholder}
          readOnly={rest.readOnly}
          onClose={() => {
            setExpanded(false);
            ref.current?.focus();
          }}
        />
      )}
    </span>
  );
}

function FullscreenEditor({
  title,
  value,
  onChange,
  maxLength,
  placeholder,
  readOnly,
  onClose,
}: {
  title: string;
  value: string;
  onChange?: TextareaHTMLAttributes<HTMLTextAreaElement>["onChange"];
  maxLength?: number;
  placeholder?: string;
  readOnly?: boolean;
  onClose: () => void;
}) {
  useEscapeKey(onClose);
  return (
    <div className="fullscreen-editor" role="dialog" aria-modal="true" aria-label={title}>
      <header className="fullscreen-editor__head">
        <h3>{title}</h3>
        <button type="button" className="btn-primary" onClick={onClose}>
          Готово
        </button>
      </header>
      <textarea
        className="fullscreen-editor__area"
        value={value}
        onChange={onChange}
        maxLength={maxLength}
        placeholder={placeholder}
        readOnly={readOnly}
        autoFocus
        aria-label={title}
      />
      {maxLength && (
        <p className="fullscreen-editor__count hint">
          {value.length} / {maxLength}
        </p>
      )}
    </div>
  );
}
