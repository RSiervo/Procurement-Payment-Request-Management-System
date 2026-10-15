import { useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react'

interface FieldProps {
  label: string
  error?: string
  hint?: string
  required?: boolean
  className?: string
  hideLabel?: boolean
}

function Field({ label, error, hint, required, className, hideLabel, id, children }: FieldProps & { id: string; children: ReactNode }) {
  return (
    <div className={`field ${className ?? ''}`}>
      <label className={hideLabel ? 'sr-only' : 'field-label'} htmlFor={id}>
        {label}
        {required && <span className="field-required" aria-hidden>*</span>}
      </label>
      {children}
      {error ? (
        <span className="field-error" id={`${id}-error`} role="alert">{error}</span>
      ) : hint ? (
        <span className="field-hint">{hint}</span>
      ) : null}
    </div>
  )
}

function controlProps(id: string, error?: string) {
  return {
    id,
    className: `input ${error ? 'input-error' : ''}`,
    'aria-invalid': error ? true : undefined,
    'aria-describedby': error ? `${id}-error` : undefined,
  }
}

type InputProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'className'> & FieldProps & { prefix?: string }

export function Input({ label, error, hint, required, className, hideLabel, prefix, ...rest }: InputProps) {
  const id = useId()
  const input = <input {...controlProps(id, error)} required={required} {...rest} />
  return (
    <Field {...{ label, error, hint, required, className, hideLabel, id }}>
      {prefix ? <div className="input-prefix"><span>{prefix}</span>{input}</div> : input}
    </Field>
  )
}

/** Native date input: every phone shows its own date wheel or calendar. */
export function DatePicker(props: Omit<InputProps, 'type' | 'prefix'>) {
  return <Input type="date" {...props} />
}

/** Decimal amount with a numeric keypad on phones. */
export function MoneyInput({ prefix = '₱', ...props }: Omit<InputProps, 'type'>) {
  return <Input type="number" inputMode="decimal" min="0" step="0.01" placeholder="0.00" prefix={prefix} {...props} />
}

type SelectProps = Omit<SelectHTMLAttributes<HTMLSelectElement>, 'className'> & FieldProps & {
  options: { value: string; label: string }[]
  placeholder?: string
}

export function Select({ label, error, hint, required, className, hideLabel, options, placeholder, ...rest }: SelectProps) {
  const id = useId()
  return (
    <Field {...{ label, error, hint, required, className, hideLabel, id }}>
      <select {...controlProps(id, error)} required={required} {...rest}>
        {placeholder !== undefined && <option value="">{placeholder}</option>}
        {options.map((option) => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
    </Field>
  )
}

type TextareaProps = Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'className'> & FieldProps

export function Textarea({ label, error, hint, required, className, hideLabel, ...rest }: TextareaProps) {
  const id = useId()
  return (
    <Field {...{ label, error, hint, required, className, hideLabel, id }}>
      <textarea {...controlProps(id, error)} required={required} {...rest} />
    </Field>
  )
}

export function Checkbox({ label, ...rest }: Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> & { label: string }) {
  return (
    <label className="check">
      <input type="checkbox" {...rest} />
      {label}
    </label>
  )
}

export function Segmented<T extends string>({ label, value, options, onChange }: {
  label: string
  value: T | null
  options: { value: T; label: string }[]
  onChange: (value: T) => void
}) {
  return (
    <div className="field">
      <span className="field-label">{label}</span>
      <div className="segmented" role="group" aria-label={label}>
        {options.map((option) => (
          <button key={option.value} type="button" aria-pressed={value === option.value} onClick={() => onChange(option.value)}>
            {option.label}
          </button>
        ))}
      </div>
    </div>
  )
}
