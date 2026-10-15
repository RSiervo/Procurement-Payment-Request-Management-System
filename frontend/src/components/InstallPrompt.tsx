import { Share, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { PortalLogo } from './PortalLogo'
import { Button } from './ui'

/** Chrome and Edge hand the page this event when the app can be installed. */
interface InstallEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

const SNOOZE_KEY = 'portal-install-snoozed'
const SNOOZE_DAYS = 14

function snoozed() {
  try {
    return Date.now() - Number(localStorage.getItem(SNOOZE_KEY) ?? 0) < SNOOZE_DAYS * 86_400_000
  } catch {
    return false
  }
}

function isInstalled() {
  return window.matchMedia('(display-mode: standalone)').matches || (navigator as { standalone?: boolean }).standalone === true
}

// iPhones and iPads have no install event; the person adds the app from the Share menu.
function isIos() {
  return /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
}

/** Offers to install the portal as an app on this device. Shown once, then not again for two weeks if declined. */
export function InstallPrompt() {
  const [event, setEvent] = useState<InstallEvent | null>(null)
  const [iosHint, setIosHint] = useState(false)

  useEffect(() => {
    if ('serviceWorker' in navigator && window.isSecureContext) {
      navigator.serviceWorker.register('/sw.js').catch(() => undefined)
    }
    if (isInstalled() || snoozed()) return
    const ready = (e: Event) => {
      e.preventDefault() // keep the browser's own mini-bar away; ours explains what it is
      setEvent(e as InstallEvent)
    }
    const done = () => setEvent(null)
    window.addEventListener('beforeinstallprompt', ready)
    window.addEventListener('appinstalled', done)
    const timer = isIos() && window.isSecureContext ? setTimeout(() => setIosHint(true), 1500) : undefined
    return () => {
      window.removeEventListener('beforeinstallprompt', ready)
      window.removeEventListener('appinstalled', done)
      clearTimeout(timer)
    }
  }, [])

  const later = () => {
    try {
      localStorage.setItem(SNOOZE_KEY, String(Date.now()))
    } catch { /* private window: it will simply be offered again */ }
    setEvent(null)
    setIosHint(false)
  }

  const install = async () => {
    if (!event) return
    await event.prompt()
    const { outcome } = await event.userChoice
    if (outcome === 'dismissed') later()
    setEvent(null)
  }

  if (!event && !iosHint) return null
  return (
    <div className="install-prompt" role="dialog" aria-label="Install the portal">
      <PortalLogo size={40} />
      <div className="install-prompt-text">
        <strong>Install the portal</strong>
        {event ? (
          <span>Open it from your desktop or home screen like any other app.</span>
        ) : (
          <span>Tap <Share size={13} aria-label="Share" style={{ verticalAlign: '-2px' }} /> then “Add to Home Screen”.</span>
        )}
      </div>
      {event && <Button size="sm" variant="primary" onClick={() => void install()}>Install</Button>}
      <button type="button" className="icon-btn" aria-label="Not now" onClick={later}><X size={16} /></button>
    </div>
  )
}
