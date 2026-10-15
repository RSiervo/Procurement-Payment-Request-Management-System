/**
 * Glass office building in perspective, used on the dashboard banner and the sign-in
 * page. Decorative only. Each pane lights up in turn so a glint travels across it
 * (see `.hero-pane` in the styles; switched off for reduced-motion users).
 */
export function BuildingArt({ className, id }: { className: string; id: string }) {
  const floors = Array.from({ length: 13 }, (_, i) => i)
  const bays = Array.from({ length: 9 }, (_, i) => i)
  // The facade is a quadrilateral; rows and columns are interpolated along its edges.
  const left = { top: [150, 6], bottom: [108, 160] }
  const right = { top: [460, -34], bottom: [460, 160] }
  const lerp = (a: number[], b: number[], t: number) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
  // A point on the facade: u runs left→right, v runs top→bottom.
  const at = (u: number, v: number) => lerp(lerp(left.top, right.top, u), lerp(left.bottom, right.bottom, u), v)
  const panes = Array.from({ length: 12 * 8 }, (_, index) => {
    const row = Math.floor(index / 8)
    const col = index % 8
    const corners = [at(col / 8, row / 12), at((col + 1) / 8, row / 12), at((col + 1) / 8, (row + 1) / 12), at(col / 8, (row + 1) / 12)]
    return { key: index, points: corners.map((p) => p.join(',')).join(' '), delay: (col * 0.45 + row * 0.3) % 7.2, bright: (row * 5 + col * 3) % 4 === 0 }
  })
  return (
    <svg className={className} viewBox="0 0 440 150" preserveAspectRatio="xMaxYMid slice" aria-hidden>
      <defs>
        <linearGradient id={`${id}-glass`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" style={{ stopColor: 'var(--art-1, #d3e4fc)' }} />
          <stop offset="0.5" style={{ stopColor: 'var(--art-2, #9dc0f5)' }} />
          <stop offset="1" style={{ stopColor: 'var(--art-3, #5b8fe0)' }} />
        </linearGradient>
        <linearGradient id={`${id}-fade`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#fff" stopOpacity="0" />
          <stop offset="0.45" stopColor="#fff" stopOpacity="0.85" />
          <stop offset="1" stopColor="#fff" stopOpacity="1" />
        </linearGradient>
        <mask id={`${id}-mask`}><rect width="440" height="150" fill={`url(#${id}-fade)`} /></mask>
      </defs>
      <g mask={`url(#${id}-mask)`}>
        <polygon points="40,70 150,6 108,160 20,160" style={{ fill: 'var(--art-2, #bfd6f8)' }} opacity="0.55" />
        <polygon points={`${left.top} ${right.top} ${right.bottom} ${left.bottom}`} fill={`url(#${id}-glass)`} />
        {panes.map((pane) => (
          <polygon key={pane.key} className={`hero-pane ${pane.bright ? 'hero-pane-bright' : ''}`} points={pane.points}
                   style={{ animationDelay: `${pane.delay}s` }} />
        ))}
        {floors.map((i) => {
          const a = lerp(left.top, left.bottom, i / 12)
          const b = lerp(right.top, right.bottom, i / 12)
          return <line key={`f${i}`} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke="#fff" strokeOpacity="0.7" strokeWidth="0.8" />
        })}
        {bays.map((i) => {
          const a = lerp(left.top, right.top, i / 8)
          const b = lerp(left.bottom, right.bottom, i / 8)
          return <line key={`b${i}`} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke="#fff" strokeOpacity="0.85" strokeWidth="1.6" />
        })}
        <polygon points="150,6 460,-34 460,10 205,60" fill="#fff" opacity="0.16" />
      </g>
    </svg>
  )
}
