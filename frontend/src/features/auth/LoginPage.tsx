import { useQuery } from '@tanstack/react-query'
import {
  AlertCircle, ArrowRight, Banknote, Eye, EyeOff, FileText, Info, Lock, Receipt, ShieldCheck, TrendingUp,
  UserRound, Users, Zap,
} from 'lucide-react'
import { useId, useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'
import { authApi } from '../../api/misc'
import { Logo } from '../../components/Logo'
import { PortalLogo } from '../../components/PortalLogo'
import { Button, Checkbox, LoadingState } from '../../components/ui'
import { useAuth } from '../../hooks/useAuth'
import { errorMessage } from '../../hooks/useToast'
import { ThemeToggle } from '../../layouts/AppLayout'

const FEATURES = [
  { icon: <FileText size={22} />, title: 'Purchase Requisition', text: 'Request and manage your purchases' },
  { icon: <Banknote size={22} />, title: 'Request for Payment', text: 'Process payments and track status' },
  { icon: <Receipt size={22} />, title: 'Reimbursement', text: 'Submit and track reimbursements' },
]
const BENEFITS = [
  { icon: <ShieldCheck size={22} />, text: ['Secure', '& Reliable'] },
  { icon: <Zap size={22} />, text: ['Fast', 'Processing'] },
  { icon: <Users size={22} />, text: ['Transparent', 'Workflow'] },
  { icon: <TrendingUp size={22} />, text: ['Better', 'Productivity'] },
]

/** "Acme Corp." → "Acme Corp" so a sentence can end with its own full stop. */
const withoutFullStop = (name: string) => name.replace(/\.+$/, '')

/** Where each "start page" setting leads after signing in. */
const LANDING: Record<string, string> = { dashboard: '/', requests: '/requests?scope=mine', approvals: '/approvals' }

export function LoginPage() {
  const { user, loading, login } = useAuth()
  const location = useLocation()
  const branding = useQuery({ queryKey: ['branding'], queryFn: authApi.branding, staleTime: Infinity, retry: false }).data
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [showHelp, setShowHelp] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const usernameId = useId()
  const passwordId = useId()

  if (loading) return <LoadingState />
  if (user) return <Navigate to={(location.state as { from?: string } | null)?.from ?? LANDING[user.preferences.landing] ?? '/'} replace />

  const company = branding?.company_name ?? ''
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!username.trim() || !password) {
      setError('Enter your username and password.')
      return
    }
    setError('')
    setBusy(true)
    try {
      await login(username.trim(), password, remember)
    } catch (err) {
      setError(errorMessage(err, 'Could not sign in. Please try again.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login">
      <aside className="login-showcase">
        <div className="login-showcase-inner">
          <div className="login-brand">
            <span className="login-brand-logo"><Logo available={branding?.has_logo} /></span>
            {company && <span className="login-brand-name">{company}</span>}
          </div>

          <div className="login-pitch">
            <h1 className="login-title">
              <span className="login-title-line"><span>Procurement <span className="login-title-amp">&amp;</span></span></span>
              <span className="login-title-line"><span className="login-title-accent">Payment Portal</span></span>
            </h1>
            <p className="login-tagline">One place to request, approve and track every purchase, payment and reimbursement.</p>
            <ul className="login-features">
              {FEATURES.map((feature) => (
                <li key={feature.title}>
                  <span className="login-feature-icon">{feature.icon}</span>
                  <span>
                    <strong>{feature.title}</strong>
                    <span>{feature.text}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>

          <ul className="login-benefits">
            {BENEFITS.map((benefit) => (
              <li key={benefit.text[0]}>
                {benefit.icon}
                <span>{benefit.text[0]}<br />{benefit.text[1]}</span>
              </li>
            ))}
          </ul>
        </div>
      </aside>

      <main className="login-main">
        <div className="login-topline">
          <span>Need help?</span>
          <button type="button" className="login-link" aria-expanded={showHelp} onClick={() => setShowHelp((v) => !v)}>Contact IT</button>
          <ThemeToggle />
        </div>

        <form className="login-card" onSubmit={submit} noValidate>
          <div className="login-card-logo">
            <PortalLogo />
            <span className="login-card-name">Procurement &amp; Payment Portal</span>
          </div>
          <div className="login-heading">
            <h2>Welcome Back</h2>
            <p>Sign in to your account to continue</p>
          </div>

          {error && <div className="alert alert-danger" role="alert"><AlertCircle size={16} />{error}</div>}
          {showHelp && (
            <div className="alert alert-info" role="status">
              <Info size={16} />
              <span>
                Sign in with your Windows username and password. If your password has expired or you are locked out,
                change it in Windows or contact the IT Security Operations team.
              </span>
            </div>
          )}

          <div className="field">
            <label className="field-label" htmlFor={usernameId}>Username or Email</label>
            <div className="login-input">
              <UserRound size={18} aria-hidden />
              <input id={usernameId} className="input" type="text" autoComplete="username" autoCapitalize="none" spellCheck={false}
                     placeholder="Your Windows username" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus />
            </div>
          </div>

          <div className="field">
            <label className="field-label" htmlFor={passwordId}>Password</label>
            <div className="login-input">
              <Lock size={18} aria-hidden />
              <input id={passwordId} className="input" type={showPassword ? 'text' : 'password'} autoComplete="current-password"
                     placeholder="Enter your password" value={password} onChange={(e) => setPassword(e.target.value)} required />
              <button type="button" className="login-reveal" onClick={() => setShowPassword((v) => !v)}
                      aria-label={showPassword ? 'Hide password' : 'Show password'} aria-pressed={showPassword}>
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          <div className="login-row">
            <Checkbox label="Remember me" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
            <Link to="/forgot-password" className="login-link">Forgot password?</Link>
          </div>

          <Button type="submit" variant="primary" block loading={busy} className="login-submit">
            {busy ? 'Signing in…' : <>Sign In<ArrowRight size={18} /></>}
          </Button>

          <p className="login-note">For authorised {withoutFullStop(company) || 'company'} personnel only. Sign-ins and activity are recorded.</p>
        </form>
      </main>
    </div>
  )
}
