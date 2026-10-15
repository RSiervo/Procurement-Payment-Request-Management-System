import { PenLine, Trash2, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { ApiError } from '../api/client'
import { authApi } from '../api/misc'
import { useAuth, useUser } from '../hooks/useAuth'
import { useToast } from '../hooks/useToast'
import { SignaturePad } from './SignaturePad'
import { Button } from './ui'

/**
 * The signed-in person's e-signature: shows the one on file and lets them upload,
 * replace or remove it. Used on the Profile page and wherever a signature is about
 * to be applied (approving, submitting), so nobody has to leave what they are doing.
 */
export function SignatureField({ purpose, allowRemove }: { purpose?: string; allowRemove?: boolean }) {
  const user = useUser()
  const { refresh } = useAuth()
  const toast = useToast()
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  // Bumped after each upload so the browser fetches the new picture.
  const [version, setVersion] = useState(0)
  const [drawing, setDrawing] = useState(false)

  const upload = async (file: File | undefined) => {
    if (!file) return
    setBusy(true)
    setError('')
    try {
      await authApi.uploadSignature(file)
      setVersion((v) => v + 1)
      refresh()
      toast.success('E-signature saved.')
    } catch (err) {
      setError(err instanceof ApiError ? err.field('file') ?? err.message : 'Could not upload the image.')
    } finally {
      setBusy(false)
      if (input.current) input.current.value = ''
    }
  }

  const remove = async () => {
    setBusy(true)
    try {
      await authApi.removeSignature()
      refresh()
    } catch (err) {
      toast.error(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="signature-field">
      <div className="signature-preview" data-empty={!user.has_signature}>
        {user.has_signature
          ? <img src={`/api/me/signature/?v=${version}`} alt="Your e-signature" />
          : <span className="signature-empty"><PenLine size={18} />No e-signature on file</span>}
      </div>
      <div className="stack-sm">
        <p className="small secondary">
          {user.has_signature
            ? purpose ?? 'This signature is printed on requests you submit and steps you approve.'
            : 'Draw your signature here, or upload a picture of it (PNG or JPG, up to 2 MB). A dark signature on a white or transparent background prints best.'}
        </p>
        {error && <p className="field-error" role="alert">{error}</p>}
        <div className="row-wrap">
          <input ref={input} type="file" accept="image/png,image/jpeg" hidden onChange={(e) => void upload(e.target.files?.[0])} />
          <Button size="sm" variant={user.has_signature ? 'secondary' : 'primary'} icon={<Upload size={14} />} loading={busy}
                  onClick={() => input.current?.click()}>
            {user.has_signature ? 'Replace' : 'Upload signature'}
          </Button>
          <Button size="sm" icon={<PenLine size={14} />} disabled={busy} onClick={() => setDrawing(true)}>Draw</Button>
          {allowRemove && user.has_signature && (
            <Button size="sm" variant="ghost" icon={<Trash2 size={14} />} disabled={busy} onClick={() => void remove()}>Remove</Button>
          )}
        </div>
      </div>
      {drawing && <SignaturePad onClose={() => setDrawing(false)} onSave={(file) => { setDrawing(false); void upload(file) }} />}
    </div>
  )
}
