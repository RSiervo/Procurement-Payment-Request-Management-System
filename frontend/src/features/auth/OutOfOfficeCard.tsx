import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { ApiError } from '../../api/client'
import { authApi } from '../../api/misc'
import { Badge, Button, Card, Input } from '../../components/ui'
import { useToast } from '../../hooks/useToast'
import type { Colleague } from '../../types'
import { formatDate, todayIso } from '../../utils/format'

/** Name a colleague to approve in your place while you are away. */
export function OutOfOfficeCard() {
  const client = useQueryClient()
  const toast = useToast()
  const { data } = useQuery({ queryKey: ['delegation'], queryFn: authApi.delegation })
  const [search, setSearch] = useState('')
  const [term, setTerm] = useState('')
  const [chosen, setChosen] = useState<Colleague | null>(null)
  const [until, setUntil] = useState('')
  const [errors, setErrors] = useState<Record<string, string[]>>({})
  const [busy, setBusy] = useState(false)

  // Wait for a pause in typing before searching.
  useEffect(() => {
    const timer = setTimeout(() => setTerm(search.trim()), 250)
    return () => clearTimeout(timer)
  }, [search])
  const found = useQuery({ queryKey: ['colleagues', term], queryFn: () => authApi.colleagues(term, true), enabled: term.length >= 2 && !chosen })

  const save = async (delegate: string | null, directoryUsername?: string) => {
    setBusy(true)
    setErrors({})
    try {
      const saved = await authApi.setDelegation(delegate, delegate || directoryUsername ? until || null : null, directoryUsername)
      client.setQueryData(['delegation'], saved)
      setChosen(null)
      setSearch('')
      setUntil('')
      toast.success(saved.delegate ? `${saved.delegate.name} can now approve in your place.` : 'Out of office switched off.')
    } catch (error) {
      if (error instanceof ApiError && Object.keys(error.errors).length) setErrors(error.errors)
      else toast.error(error)
    } finally {
      setBusy(false)
    }
  }

  const cover = data?.delegate
  return (
    <Card title="Out of office" actions={cover && <Badge tone="success">On</Badge>}>
      <div className="stack">
        {!!data?.covering_for.length && (
          <div className="alert alert-info">You are currently approving in place of {data.covering_for.join(', ')}.</div>
        )}
        {cover ? (
          <>
            <p className="small">
              <span className="strong">{cover.name}</span>{cover.department_name ? ` (${cover.department_name})` : ''} approves in your place
              {data?.until ? ` until ${formatDate(data.until)}` : ' until you switch this off'}. You can still approve yourself.
            </p>
            <div><Button loading={busy} onClick={() => void save(null)}>Switch off</Button></div>
          </>
        ) : (
          <>
            <div className="form-grid">
              {chosen ? (
                <div className="field">
                  <span className="field-label">Colleague who approves for me</span>
                  <div className="row between">
                    <div><div className="strong">{chosen.name}</div><div className="xs muted">{chosen.department_name || chosen.email}{chosen.id ? '' : ' · an account will be created for them'}</div></div>
                    <Button size="sm" onClick={() => setChosen(null)}>Change</Button>
                  </div>
                  {errors.delegate && <span className="field-error">{errors.delegate[0]}</span>}
                </div>
              ) : (
                <div>
                  <Input label="Colleague who approves for me" type="search" placeholder="Type a name or email…" value={search}
                         error={errors.delegate?.[0]} onChange={(e) => setSearch(e.target.value)} />
                  {term.length >= 2 && found.data && (
                    <div className="stack-sm" style={{ marginTop: 6, gap: 4 }}>
                      {found.data.length === 0 && <span className="xs muted">No active colleague matches “{term}”.</span>}
                      {found.data.map((person) => (
                        <button key={person.id ?? person.directory_username} type="button" className="btn btn-sm" style={{ justifyContent: 'flex-start' }}
                                onClick={() => setChosen(person)}>
                          {person.name}<span className="muted">{person.department_name ? ` · ${person.department_name}` : ''}{person.id ? '' : ' · not in the portal yet'}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
              <Input label="Until (optional)" type="date" min={todayIso()} value={until} error={errors.until?.[0]}
                     hint="Leave empty to keep it on until you switch it off." onChange={(e) => setUntil(e.target.value)} />
            </div>
            <div><Button variant="primary" loading={busy} disabled={!chosen} onClick={() => chosen && void save(chosen.id, chosen.directory_username)}>Switch on</Button></div>
            <p className="field-hint">
              While this is on, the colleague you name sees and can approve whatever is waiting for you, signing with their own
              e-signature. The request history records that they approved on your behalf. They can never approve their own requests this way.
            </p>
          </>
        )}
      </div>
    </Card>
  )
}
