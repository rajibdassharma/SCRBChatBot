import { useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';

/**
 * Password input with a show/hide toggle. Used everywhere a password is
 * entered (login, change-password) or displayed once (admin-generated
 * temp password). Renders a standard text input with a button-icon on
 * the right edge that flips `type="password"` ↔ `type="text"`.
 *
 * Inherits the KSP-branded styling used across the app.
 */
type PasswordInputProps = {
  value: string;
  onChange?: (e: React.ChangeEvent<HTMLInputElement>) => void;
  placeholder?: string;
  required?: boolean;
  autoComplete?: string;
  readOnly?: boolean;
  /** Accessible label for the toggle button. Defaults to "Show password". */
  toggleLabel?: string;
};

export function PasswordInput({
  value,
  onChange,
  placeholder,
  required,
  autoComplete,
  readOnly,
  toggleLabel = 'Show password',
}: PasswordInputProps) {
  const [visible, setVisible] = useState(false);

  return (
    <div className="relative">
      <input
        type={visible ? 'text' : 'password'}
        value={value}
        onChange={onChange}
        required={required}
        autoComplete={autoComplete}
        readOnly={readOnly}
        placeholder={placeholder}
        className="w-full px-4 py-2.5 pr-11 rounded-xl text-sm outline-none transition"
        style={{ border: '2px solid var(--ksp-navy)' }}
      />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? 'Hide password' : toggleLabel}
        title={visible ? 'Hide password' : toggleLabel}
        tabIndex={-1}
        className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-md hover:bg-gray-100 transition"
        style={{ color: 'var(--ksp-navy)' }}
      >
        {visible ? <EyeOff size={18} /> : <Eye size={18} />}
      </button>
    </div>
  );
}
