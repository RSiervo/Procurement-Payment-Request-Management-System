import { useEffect, useRef, useState, type CSSProperties, type PointerEvent } from 'react'
import { hexToRgb, hsvToRgb, isHex, rgbToHex, rgbToHsv } from '../utils/colour'

/**
 * A colour wheel: the angle is the hue, the distance from the centre is how vivid it is,
 * and the slider underneath sets the brightness. `onPreview` fires while dragging,
 * `onCommit` when the person lets go (or finishes typing a colour code).
 */
export function ColourWheel({ value, onPreview, onCommit }: {
  value: string
  onPreview: (hex: string) => void
  onCommit: (hex: string) => void
}) {
  const [hsv, setHsv] = useState(() => rgbToHsv(hexToRgb(value)))
  const [text, setText] = useState(value)
  const dragging = useRef(false)
  const hex = rgbToHex(hsvToRgb(...hsv))

  // Follow a colour set from outside (for example when the saved one loads).
  useEffect(() => {
    if (value !== rgbToHex(hsvToRgb(...hsv))) {
      setHsv(rgbToHsv(hexToRgb(value)))
      setText(value)
    }
  }, [value]) // oxlint-disable-line react-hooks/exhaustive-deps

  const change = (next: [number, number, number]) => {
    setHsv(next)
    const colour = rgbToHex(hsvToRgb(...next))
    setText(colour)
    onPreview(colour)
    return colour
  }

  const fromPointer = (event: PointerEvent<HTMLDivElement>) => {
    const box = event.currentTarget.getBoundingClientRect()
    const x = event.clientX - box.left - box.width / 2
    const y = event.clientY - box.top - box.height / 2
    const hue = (Math.atan2(y, x) * 180 / Math.PI + 90 + 360) % 360 // red at the top, like the gradient
    const saturation = Math.min(1, Math.hypot(x, y) / (box.width / 2))
    return change([hue, saturation, hsv[2]])
  }

  const step = (dh: number, ds: number) => onCommit(change([(hsv[0] + dh + 360) % 360, Math.min(1, Math.max(0, hsv[1] + ds)), hsv[2]]))
  const angle = (hsv[0] - 90) * Math.PI / 180

  return (
    <div className="colour-wheel">
      <div className="colour-wheel-disc" role="slider" tabIndex={0} aria-label="Colour: arrow keys change hue and vividness"
           aria-valuetext={hex} aria-valuenow={Math.round(hsv[0])} aria-valuemin={0} aria-valuemax={360}
           style={{ '--wheel-brightness': 0.35 + hsv[2] * 0.65 } as CSSProperties}
           onPointerDown={(event) => { event.currentTarget.setPointerCapture(event.pointerId); dragging.current = true; fromPointer(event) }}
           onPointerMove={(event) => { if (dragging.current) fromPointer(event) }}
           onPointerUp={(event) => { if (dragging.current) { dragging.current = false; onCommit(fromPointer(event)) } }}
           onKeyDown={(event) => {
             const move = { ArrowLeft: [-5, 0], ArrowRight: [5, 0], ArrowUp: [0, 0.05], ArrowDown: [0, -0.05] }[event.key]
             if (move) { event.preventDefault(); step(move[0], move[1]) }
           }}>
        <span className="colour-wheel-thumb" style={{
          left: `${50 + Math.cos(angle) * hsv[1] * 50}%`, top: `${50 + Math.sin(angle) * hsv[1] * 50}%`, background: hex,
        }} />
      </div>
      <div className="colour-wheel-side">
        <label className="field-label" htmlFor="colour-brightness">Brightness</label>
        <input id="colour-brightness" type="range" min="20" max="100" value={Math.round(hsv[2] * 100)} className="colour-wheel-range"
               style={{ background: `linear-gradient(90deg, #000, ${rgbToHex(hsvToRgb(hsv[0], hsv[1], 1))})` }}
               onChange={(event) => change([hsv[0], hsv[1], Number(event.target.value) / 100])}
               onPointerUp={() => onCommit(hex)} onKeyUp={() => onCommit(hex)} />
        <label className="field-label" htmlFor="colour-code">Colour code</label>
        <div className="colour-wheel-code">
          <span className="colour-wheel-chip" style={{ background: hex }} />
          <input id="colour-code" className="input" value={text} maxLength={7} spellCheck={false} aria-describedby="colour-code-hint"
                 onChange={(event) => {
                   const typed = event.target.value.trim()
                   setText(typed)
                   if (isHex(typed)) {
                     setHsv(rgbToHsv(hexToRgb(typed)))
                     onPreview(typed.toLowerCase())
                   }
                 }}
                 onBlur={() => (isHex(text) ? onCommit(text.toLowerCase()) : setText(hex))}
                 onKeyDown={(event) => { if (event.key === 'Enter' && isHex(text)) onCommit(text.toLowerCase()) }} />
        </div>
        <span className="field-hint" id="colour-code-hint">For example #2160e0.</span>
      </div>
    </div>
  )
}
