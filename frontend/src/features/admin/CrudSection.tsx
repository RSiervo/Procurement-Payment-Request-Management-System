import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import { useState, type FormEvent, type ReactNode } from 'react'
import { ApiError } from '../../api/client'
import {
  Button, Card, Checkbox, ConfirmationDialog, DataTable, EmptyState, Input, Modal, Select, Textarea, type Column,
} from '../../components/ui'
import { useDebounced } from '../../hooks/useLookups'
import { useToast } from '../../hooks/useToast'

export interface FieldDef {
  name: string
  label: string
  type?: 'text' | 'email' | 'password' | 'number' | 'textarea' | 'select' | 'checkbox' | 'multiselect'
  options?: { value: string; label: string }[]
  required?: boolean
  hint?: string
  wide?: boolean
  /** Hide the field when editing (or creating) a record. */
  only?: 'create' | 'edit'
}

type Values = Record<string, unknown>

interface Props<T extends { id: string }> {
  title: string
  description?: string
  noun: string
  queryKey: string
  list: (search: string) => Promise<T[]>
  create?: (values: Values) => Promise<unknown>
  update: (id: string, values: Values) => Promise<unknown>
  remove?: (id: string) => Promise<unknown>
  canRemove?: (row: T) => boolean
  searchable?: boolean
  columns: Column<T>[]
  card: (row: T) => ReactNode
  fields: FieldDef[]
  blank: Values
  /** Map a record to form values when they differ (e.g. drop read-only fields). */
  toValues?: (row: T) => Values
}

/** List + create/edit dialog for one kind of reference data. */
export function CrudSection<T extends { id: string }>(props: Props<T>) {
  const { title, description, noun, queryKey, columns, fields, blank } = props
  const client = useQueryClient()
  const toast = useToast()
  const [search, setSearch] = useState('')
  const term = useDebounced(search)
  const [editing, setEditing] = useState<{ row: T | null; values: Values } | null>(null)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [removing, setRemoving] = useState<T | null>(null)
  const query = useQuery({ queryKey: ['admin', queryKey, term], queryFn: () => props.list(term) })

  const refresh = () => {
    void client.invalidateQueries({ queryKey: ['admin'] })
    void client.invalidateQueries({ queryKey: ['lookups'] })
  }
  const open = (row: T | null) => {
    setErrors({})
    setEditing({ row, values: row ? props.toValues?.(row) ?? pick(row, fields) : { ...blank } })
  }
  const setValue = (name: string, value: unknown) => setEditing((current) => current && { ...current, values: { ...current.values, [name]: value } })

  const save = async (event: FormEvent) => {
    event.preventDefault()
    if (!editing) return
    setBusy(true)
    setErrors({})
    try {
      const values = clean(editing.values, fields)
      if (editing.row) await props.update(editing.row.id, values)
      else await props.create?.(values)
      toast.success(`${noun} saved.`)
      setEditing(null)
      refresh()
    } catch (error) {
      if (error instanceof ApiError && Object.keys(error.errors).length) {
        setErrors(Object.fromEntries(Object.entries(error.errors).map(([key, value]) => [key, Array.isArray(value) ? String(value[0]) : String(value)])))
      } else {
        toast.error(error)
      }
    } finally {
      setBusy(false)
    }
  }

  const visibleFields = fields.filter((field) => !field.only || field.only === (editing?.row ? 'edit' : 'create'))
  const actionColumn: Column<T> = {
    header: '',
    align: 'right',
    render: (row) => (
      <div className="row" style={{ justifyContent: 'flex-end', gap: 0 }}>
        <button type="button" className="icon-btn" aria-label={`Edit ${noun.toLowerCase()}`} onClick={() => open(row)}><Pencil size={16} /></button>
        {props.remove && (props.canRemove?.(row) ?? true) && (
          <button type="button" className="icon-btn" aria-label={`Delete ${noun.toLowerCase()}`} onClick={() => setRemoving(row)}><Trash2 size={16} /></button>
        )}
      </div>
    ),
  }

  return (
    <Card flush title={title} actions={props.create && <Button size="sm" variant="primary" icon={<Plus size={15} />} onClick={() => open(null)}>Add {noun.toLowerCase()}</Button>}>
      {(description || props.searchable) && (
        <div className="stack-sm" style={{ padding: 16, borderBottom: '1px solid var(--border)' }}>
          {description && <p className="small secondary">{description}</p>}
          {props.searchable && <Input label="Search" hideLabel type="search" placeholder={`Search ${title.toLowerCase()}…`} value={search} onChange={(e) => setSearch(e.target.value)} />}
        </div>
      )}
      <DataTable
        rows={query.data}
        loading={query.isLoading}
        rowKey={(row) => row.id}
        columns={[...columns, actionColumn]}
        empty={<EmptyState title={`No ${title.toLowerCase()} yet`} />}
        card={(row) => (
          <div className="row between" style={{ alignItems: 'flex-start' }}>
            <div className="stack-sm grow" style={{ gap: 4 }}>{props.card(row)}</div>
            {actionColumn.render(row)}
          </div>
        )}
      />

      {editing && (
        <Modal title={`${editing.row ? 'Edit' : 'Add'} ${noun.toLowerCase()}`} onClose={() => setEditing(null)} wide
               footer={<>
                 <Button onClick={() => setEditing(null)} disabled={busy}>Cancel</Button>
                 <Button variant="primary" type="submit" form="crud-form" loading={busy}>Save</Button>
               </>}>
          <form id="crud-form" className="form-grid" onSubmit={save}>
            {visibleFields.map((field) => {
              const value = editing.values[field.name]
              const common = { label: field.label, hint: field.hint, required: field.required, error: errors[field.name], className: field.wide ? 'span-2' : undefined }
              if (field.type === 'checkbox') {
                return <Checkbox key={field.name} label={field.label} checked={!!value} onChange={(e) => setValue(field.name, e.target.checked)} />
              }
              if (field.type === 'select') {
                return <Select key={field.name} {...common} placeholder={field.required ? 'Select' : 'None'} options={field.options ?? []}
                               value={(value as string) ?? ''} onChange={(e) => setValue(field.name, e.target.value)} />
              }
              if (field.type === 'multiselect') {
                const selected = (value as string[]) ?? []
                return (
                  <fieldset key={field.name} className="field span-2" style={{ border: 0, padding: 0, margin: 0 }}>
                    <legend className="field-label" style={{ padding: 0, marginBottom: 4 }}>{field.label}</legend>
                    <div className="row-wrap" style={{ gap: '0 20px' }}>
                      {(field.options ?? []).map((option) => (
                        <Checkbox key={option.value} label={option.label} checked={selected.includes(option.value)}
                                  onChange={(e) => setValue(field.name, e.target.checked ? [...selected, option.value] : selected.filter((v) => v !== option.value))} />
                      ))}
                    </div>
                    {errors[field.name] && <span className="field-error">{errors[field.name]}</span>}
                  </fieldset>
                )
              }
              if (field.type === 'textarea') {
                return <Textarea key={field.name} {...common} className="span-2" rows={6} value={(value as string) ?? ''} onChange={(e) => setValue(field.name, e.target.value)} />
              }
              return <Input key={field.name} {...common} type={field.type ?? 'text'} value={(value as string | number) ?? ''}
                            autoComplete={field.type === 'password' ? 'new-password' : 'off'} onChange={(e) => setValue(field.name, e.target.value)} />
            })}
          </form>
        </Modal>
      )}
      {removing && props.remove && (
        <ConfirmationDialog title={`Delete this ${noun.toLowerCase()}?`} confirmLabel="Delete" danger
                            message="This cannot be undone. Records that are in use cannot be deleted; deactivate them instead."
                            onConfirm={async () => {
                              try {
                                await props.remove!(removing.id)
                                toast.success(`${noun} deleted.`)
                                refresh()
                              } catch (error) { toast.error(error) }
                            }}
                            onClose={() => setRemoving(null)} />
      )}
    </Card>
  )
}

function pick(row: object, fields: FieldDef[]): Values {
  const source = row as Values
  return Object.fromEntries(fields.map((field) => [field.name, field.type === 'password' ? '' : source[field.name] ?? (field.type === 'multiselect' ? [] : '')]))
}

/** Empty optional selects and numbers go to the server as null, not "". */
function clean(values: Values, fields: FieldDef[]): Values {
  const result: Values = {}
  for (const field of fields) {
    const value = values[field.name]
    if (value === undefined) continue
    if (field.type === 'password' && !value) continue
    result[field.name] = (field.type === 'select' || field.type === 'number') && value === '' ? null : value
  }
  return result
}
