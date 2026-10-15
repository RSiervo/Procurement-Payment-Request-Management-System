import { ArrowLeft, MailCheck } from 'lucide-react'
import { useState, type FormEvent, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ApiError } from '../../api/client'
import { authApi } from '../../api/misc'
import { PortalLogo } from '../../components/PortalLogo'
import { Button, Input } from '../../components/ui'
import { errorMessage } from '../../hooks/useToast'

function Shell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="verify-page">
      <div className="verify-card">
        <div className="verify-brand"><PortalLogo size={30} /><span>Procurement &amp; Payment Portal</span></div>
        <h1 className="reset-title">{title}</h1>
        {children}
        <Link to="/login" className="reset-back"><ArrowLeft size={14} />Back to sign in</Link>
      </div>
    </div>
  )
}

/** Ask for a reset link. The answer is the same whether or not the address has an account. */
export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await authApi.requestPasswordReset(email)
      setSent(true)
    } catch (err) {
      setError(err instanceof ApiError && err.status === 429 ? 'Too many attempts. Please try again in an hour.' : errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Shell title="Forgot your password?">
      {sent ? (
        <div className="verify-banner" data-tone="success"><MailCheck size={22} />
          <div>
            <strong>Check your email</strong>
            <span>If {email} has an account, a message with instructions is on its way. The link in it works for one hour.</span>
          </div>
        </div>
      ) : (
        <form className="stack" onSubmit={submit}>
          <p className="small secondary">
            Enter the email address of your portal account and we will send you a link to choose a new password.
            If you sign in with your Windows username, your password is your Windows password: change it in Windows or ask IT.
          </p>
          <Input label="Email address" type="email" autoComplete="email" required value={email} error={error}
                 onChange={(e) => setEmail(e.target.value)} />
          <Button type="submit" variant="primary" block loading={busy}>Send reset link</Button>
        </form>
      )}
    </Shell>
  )
}

/** Where the emailed link lands: choose the new password. */
export function ResetPasswordPage() {
  const [params] = useSearchParams()
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const [errors, setErrors] = useState<{ password?: string; confirm?: string; form?: string }>({})
  const uid = params.get('uid') ?? ''
  const token = params.get('token') ?? ''

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (password !== confirm) {
      setErrors({ confirm: 'The two passwords do not match.' })
      return
    }
    setBusy(true)
    setErrors({})
    try {
      await authApi.confirmPasswordReset(uid, token, password)
      setDone(true)
    } catch (err) {
      const field = err instanceof ApiError ? err.field('new_password') : undefined
      setErrors(field ? { password: field } : { form: errorMessage(err) })
    } finally {
      setBusy(false)
    }
  }

  if (!uid || !token) {
    return (
      <Shell title="Reset your password">
        <div className="verify-banner" data-tone="danger"><div><strong>This link is incomplete</strong>
          <span>Open the link from the email again, or ask for a new one.</span></div></div>
        <Link to="/forgot-password" className="btn btn-primary">Ask for a new link</Link>
      </Shell>
    )
  }
  return (
    <Shell title="Choose a new password">
      {done ? (
        <div className="verify-banner" data-tone="success"><MailCheck size={22} />
          <div><strong>Password changed</strong><span>You can sign in with your new password now. Other devices have been signed out.</span></div>
        </div>
      ) : (
        <form className="stack" onSubmit={submit}>
          {errors.form && (
            <div className="verify-banner" data-tone="danger"><div><strong>{errors.form}</strong>
              <span><Link to="/forgot-password">Ask for a new link</Link></span></div></div>
          )}
          <Input label="New password" type="password" autoComplete="new-password" required value={password} error={errors.password}
                 hint="At least 10 characters, not a common password." onChange={(e) => setPassword(e.target.value)} />
          <Input label="Confirm new password" type="password" autoComplete="new-password" required value={confirm} error={errors.confirm}
                 onChange={(e) => setConfirm(e.target.value)} />
          <Button type="submit" variant="primary" block loading={busy}>Change password</Button>
        </form>
      )}
    </Shell>
  )
}
