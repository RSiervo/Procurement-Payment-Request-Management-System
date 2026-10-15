import { Check, KeyRound, LayoutDashboard, Mail, Palette, PenLine, Plane } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { useState, type FormEvent } from 'react'
import { ApiError } from '../../api/client'
import { authApi } from '../../api/misc'
import { ColourWheel } from '../../components/ColourWheel'
import { SignatureField } from '../../components/SignatureField'
import { Button, Card, Checkbox, Input, Segmented, Select } from '../../components/ui'
import { useAuth, useUser } from '../../hooks/useAuth'
import { applyAccent, applyDisplay, useTheme } from '../../hooks/useTheme'
import { useToast } from '../../hooks/useToast'
import type { Preferences } from '../../types'
import { deriveTheme, isHex } from '../../utils/colour'
import { THEMES } from '../../utils/themes'
import { OutOfOfficeCard } from './OutOfOfficeCard'

const SECTIONS = [
  { group: 'Look and feel', value: 'appearance', label: 'Appearance', icon: <Palette size={16} /> },
  { group: 'Look and feel', value: 'display', label: 'Display', icon: <LayoutDashboard size={16} /> },
  { group: 'Approvals', value: 'email', label: 'Email notifications', icon: <Mail size={16} /> },
  { group: 'Approvals', value: 'away', label: 'Out of office', icon: <Plane size={16} /> },
  { group: 'Approvals', value: 'signature', label: 'E-signature', icon: <PenLine size={16} /> },
  { group: 'Account', value: 'password', label: 'Password', icon: <KeyRound size={16} /> },
] as const
const GROUPS = ['Look and feel', 'Approvals', 'Account'] as const

/** The signed-in person's own configuration, one section at a time: looks, emails, cover, e-signature, password. */
export function SettingsPage() {
  const user = useUser()
  const { refresh } = useAuth()
  const toast = useToast()
  const { theme: mode, setTheme: setMode } = useTheme()
  const [params, setParams] = useSearchParams()
  const tab = SECTIONS.find((section) => section.value === params.get('tab'))?.value ?? 'appearance'
  const choose = (value: string) => setParams({ tab: value }, { replace: true })
  const [passwords, setPasswords] = useState({ current: '', next: '', confirm: '' })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState<'password' | 'theme' | null>(null)

  const isCustom = isHex(user.theme ?? '')
  const [wheelOpen, setWheelOpen] = useState(true)
  // Where the wheel starts the first time: the colour of the theme in use.
  const lastCustom = THEMES.find((option) => option.id === (user.theme ?? ''))?.brand ?? '#2160e0'

  const chooseTheme = async (id: string) => {
    const previous = user.theme ?? ''
    if (id === previous) return
    applyAccent(id) // show it straight away
    // Dragging the wheel saves quietly; only picking a swatch locks the row while it saves.
    if (!isHex(id) || !isHex(previous)) setBusy('theme')
    try {
      await authApi.updateTheme(id)
      refresh()
    } catch (error) {
      applyAccent(previous)
      toast.error(error)
    } finally {
      setBusy(null)
    }
  }

  // Settings save as soon as they are changed. The screen shows the new value at once
  // and goes back to the saved one if the server refuses it.
  const [pending, setPending] = useState<Partial<Preferences>>({})
  const prefs = { ...user.preferences, ...pending }
  const setPref = async (patch: Partial<Preferences>) => {
    const next = { ...prefs, ...patch }
    setPending((current) => ({ ...current, ...patch }))
    applyDisplay(next.density, next.motion)
    try {
      await authApi.updatePreferences(patch)
      refresh()
    } catch (error) {
      setPending((current) => {
        const rest = { ...current }
        for (const key of Object.keys(patch) as (keyof Preferences)[]) delete rest[key]
        return rest
      })
      applyDisplay(user.preferences.density, user.preferences.motion)
      toast.error(error)
    }
  }

  const changePassword = async (event: FormEvent) => {
    event.preventDefault()
    if (passwords.next !== passwords.confirm) {
      setErrors({ confirm: 'The two passwords do not match.' })
      return
    }
    setErrors({})
    setBusy('password')
    try {
      await authApi.changePassword(passwords.current, passwords.next)
      setPasswords({ current: '', next: '', confirm: '' })
      toast.success('Password changed. Other devices have been signed out.')
    } catch (error) {
      if (error instanceof ApiError && Object.keys(error.errors).length) {
        setErrors({ current: error.field('current_password') ?? '', next: error.field('new_password') ?? '' })
      } else {
        toast.error(error)
      }
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Settings</h1>
          <p>Your own preferences. They apply to your account only.</p>
        </div>
      </div>

      <div className="admin-layout settings-layout">
        {/* Sections down the left on wide screens; a single dropdown on phones. */}
        <nav className="admin-nav" aria-label="Settings sections">
          {GROUPS.map((group) => (
            <div key={group} className="admin-nav-group">
              <span className="admin-nav-heading">{group}</span>
              {SECTIONS.filter((section) => section.group === group).map((section) => (
                <button key={section.value} type="button" className="admin-nav-item" aria-current={tab === section.value ? 'page' : undefined}
                        onClick={() => choose(section.value)}>
                  {section.icon}<span>{section.label}</span>
                </button>
              ))}
            </div>
          ))}
        </nav>
        <Select label="Section" hideLabel className="admin-nav-select" value={tab} onChange={(e) => choose(e.target.value)}
                options={SECTIONS.map((section) => ({ value: section.value, label: section.label }))} />
        <div className="admin-content">
      {tab === 'appearance' && (<Card title="Appearance">
        <div className="stack">
          <Segmented label="Mode" value={mode} onChange={setMode}
                     options={[{ value: 'light', label: 'Light' }, { value: 'dark', label: 'Dark' }]} />
          <div className="field">
            <span className="field-label">Colour theme</span>
            <div className="theme-grid" role="radiogroup" aria-label="Colour theme">
              {THEMES.map((option) => {
                const chosen = (user.theme ?? '') === option.id
                return (
                  <button key={option.id || 'ocean'} type="button" role="radio" aria-checked={chosen} className="theme-swatch"
                          disabled={busy === 'theme'} onClick={() => void chooseTheme(option.id)}>
                    <span className="theme-swatch-color" style={{ background: `linear-gradient(135deg, ${option.brand}, ${option.brand2})` }}>
                      {chosen && <Check size={20} strokeWidth={3} />}
                    </span>
                    {option.name}
                  </button>
                )
              })}
              <button type="button" role="radio" aria-checked={isCustom} className="theme-swatch" disabled={busy === 'theme'}
                      onClick={() => (isCustom ? setWheelOpen((open) => !open) : void chooseTheme(lastCustom))}>
                <span className="theme-swatch-color theme-swatch-custom">{isCustom && <Check size={20} strokeWidth={3} />}</span>
                Custom
              </button>
            </div>
            {isCustom && wheelOpen && (
              <div className="theme-custom">
                <ColourWheel value={user.theme} onPreview={applyAccent} onCommit={(hex) => void chooseTheme(hex)} />
                {deriveTheme(user.theme).adjusted && (
                  <p className="field-hint">This colour is used a little darker on buttons, so that white text on them stays readable.</p>
                )}
              </div>
            )}
            <span className="field-hint">
              Your colour theme is saved to your account and follows you to any device. Light or dark is remembered per device.
              Status colours and chart colours stay the same in every theme.
            </span>
          </div>
        </div>
      </Card>)}

      {tab === 'display' && (<Card title="Display">
        <div className="form-grid">
          <Segmented label="Layout size" value={prefs.density} onChange={(density) => void setPref({ density })}
                     options={[{ value: 'auto', label: 'Auto' }, { value: 'compact', label: 'Compact' }, { value: 'comfortable', label: 'Comfortable' }]} />
          <Segmented label="Animations" value={prefs.motion} onChange={(motion) => void setPref({ motion })}
                     options={[{ value: 'on', label: 'On' }, { value: 'off', label: 'Off' }]} />
          <Select label="Rows per page in lists" value={String(prefs.page_size)}
                  onChange={(e) => void setPref({ page_size: Number(e.target.value) as Preferences['page_size'] })}
                  options={[{ value: '10', label: '10 rows' }, { value: '20', label: '20 rows' }, { value: '50', label: '50 rows' }]} />
          <Select label="Start page after signing in" value={prefs.landing}
                  onChange={(e) => void setPref({ landing: e.target.value as Preferences['landing'] })}
                  options={[{ value: 'dashboard', label: 'Dashboard' }, { value: 'requests', label: 'My Requests' }, { value: 'approvals', label: 'Approvals' }]} />
        </div>
        <p className="field-hint" style={{ marginTop: 12 }}>
          Layout size: Auto shrinks pages on short laptop screens only; Compact always shows more on screen; Comfortable keeps
          everything full size. On phones the layout is always the same.
        </p>
      </Card>)}

      {tab === 'email' && (<Card title="Email notifications">
        <div className="stack-sm">
          <Checkbox label="When something is waiting for me: approvals, questions, and requests returned to me"
                    checked={prefs.email_action} onChange={(e) => void setPref({ email_action: e.target.checked })} />
          <Checkbox label="Progress on requests I am involved in: approved, received by OPS, completed, rejected"
                    checked={prefs.email_updates} onChange={(e) => void setPref({ email_updates: e.target.checked })} />
          <Checkbox label="New comments on my requests"
                    checked={prefs.email_comments} onChange={(e) => void setPref({ email_comments: e.target.checked })} />
          <Checkbox label="A morning summary of what is waiting for me (only sent when there is something)"
                    checked={prefs.email_digest} onChange={(e) => void setPref({ email_digest: e.target.checked })} />
          <p className="field-hint">
            These control emails only. Notifications inside the portal (the bell) are always kept, so nothing is missed.
          </p>
        </div>
      </Card>)}

      {tab === 'away' && <OutOfOfficeCard />}

      {tab === 'signature' && (<Card title="E-signature">
        <SignatureField allowRemove />
      </Card>)}

      {tab === 'password' && (<Card title="Password">
        {user.is_directory_user ? (
          <p className="small secondary">
            You sign in with your Windows (Active Directory) account, so your password is changed in Windows, not here.
          </p>
        ) : (
          <form className="stack" onSubmit={changePassword}>
            <Input label="Current password" type="password" autoComplete="current-password" required
                   value={passwords.current} error={errors.current}
                   onChange={(e) => setPasswords({ ...passwords, current: e.target.value })} />
            <div className="form-grid">
              <Input label="New password" type="password" autoComplete="new-password" required
                     hint="At least 10 characters, not a common password." value={passwords.next} error={errors.next}
                     onChange={(e) => setPasswords({ ...passwords, next: e.target.value })} />
              <Input label="Confirm new password" type="password" autoComplete="new-password" required
                     value={passwords.confirm} error={errors.confirm}
                     onChange={(e) => setPasswords({ ...passwords, confirm: e.target.value })} />
            </div>
            <div><Button type="submit" variant="primary" loading={busy === 'password'}>Change password</Button></div>
          </form>
        )}
      </Card>)}
        </div>
      </div>
    </div>
  )
}
