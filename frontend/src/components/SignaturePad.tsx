import { Eraser } from 'lucide-react'
import { useEffect, useRef, useState, type PointerEvent } from 'react'
import { Button, Modal } from './ui'

const WIDTH = 600
const HEIGHT = 240

/** Sign with a finger, pen or mouse. Saves a PNG with a transparent background, like an uploaded signature. */
export function SignaturePad({ onSave, onClose }: { onSave: (file: File) => void; onClose: () => void }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const last = useRef<{ x: number; y: number } | null>(null)
  const [signed, setSigned] = useState(false)

  useEffect(() => {
    const context = canvas.current?.getContext('2d')
    if (!context) return
    context.lineWidth = 3.2
    context.lineCap = 'round'
    context.lineJoin = 'round'
    context.strokeStyle = '#0f1b3d'
    context.fillStyle = '#0f1b3d'
  }, [])

  // The canvas is drawn at a fixed size and scaled by CSS, so pointer positions are scaled back.
  const point = (event: PointerEvent<HTMLCanvasElement>) => {
    const box = event.currentTarget.getBoundingClientRect()
    return { x: ((event.clientX - box.left) / box.width) * WIDTH, y: ((event.clientY - box.top) / box.height) * HEIGHT }
  }

  const start = (event: PointerEvent<HTMLCanvasElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId)
    const at = point(event)
    last.current = at
    const context = canvas.current!.getContext('2d')!
    context.beginPath()
    context.arc(at.x, at.y, 1.6, 0, Math.PI * 2) // a tap leaves a dot
    context.fill()
    setSigned(true)
  }

  const move = (event: PointerEvent<HTMLCanvasElement>) => {
    if (!last.current) return
    const at = point(event)
    const context = canvas.current!.getContext('2d')!
    context.beginPath()
    context.moveTo(last.current.x, last.current.y)
    context.lineTo(at.x, at.y)
    context.stroke()
    last.current = at
  }

  const end = () => {
    last.current = null
  }

  const clear = () => {
    canvas.current!.getContext('2d')!.clearRect(0, 0, WIDTH, HEIGHT)
    setSigned(false)
  }

  const save = () => {
    canvas.current!.toBlob((blob) => {
      if (blob) onSave(new File([blob], 'signature.png', { type: 'image/png' }))
    }, 'image/png')
  }

  return (
    <Modal title="Draw your signature" onClose={onClose}
           footer={<>
             <Button icon={<Eraser size={15} />} disabled={!signed} onClick={clear}>Clear</Button>
             <Button variant="primary" disabled={!signed} onClick={save}>Use this signature</Button>
           </>}>
      <div className="stack-sm">
        <canvas ref={canvas} className="signature-pad" width={WIDTH} height={HEIGHT} aria-label="Signature drawing area"
                onPointerDown={start} onPointerMove={move} onPointerUp={end} onPointerCancel={end} />
        <p className="field-hint">Sign inside the box with your finger, a pen or the mouse. It replaces the signature on file.</p>
      </div>
    </Modal>
  )
}
