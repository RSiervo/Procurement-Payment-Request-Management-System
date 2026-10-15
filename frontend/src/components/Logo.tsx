import { FileText } from 'lucide-react'
import { useState } from 'react'

let logoMissing = false

/**
 * The company logo uploaded under Administration → System, or a neutral mark until one exists.
 * Pass `available` when the caller already knows (from the system configuration) whether a
 * logo exists; without it the image is tried once and the mark is used if it fails.
 */
export function Logo({ available }: { available?: boolean }) {
  const [failed, setFailed] = useState(logoMissing)
  if (available === false || failed) {
    return <span className="brand-mark" aria-hidden><FileText size={18} /></span>
  }
  return (
    <img className="brand-logo" src="/api/system-config/logo/" alt="Company logo"
         onError={() => { logoMissing = true; setFailed(true) }} />
  )
}
