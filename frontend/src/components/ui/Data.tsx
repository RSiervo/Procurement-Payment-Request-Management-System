import { ChevronLeft, ChevronRight, FileText, Image as ImageIcon, Paperclip, Trash2, Upload } from 'lucide-react'
import { useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { useIsDesktop } from '../../hooks/useLookups'
import type { Attachment } from '../../types'
import { fileSize, formatDate } from '../../utils/format'
import { Button } from './Button'
import { EmptyState, LoadingState } from './Display'

export interface Column<T> {
  header: string
  render: (row: T) => ReactNode
  align?: 'right'
  width?: string
  /** Drop this column when the table gets narrow: 'first' goes before 'second'. */
  dropWhenNarrow?: 'first' | 'second'
}

function cellClass<T>(column: Column<T>): string | undefined {
  return [column.align, column.dropWhenNarrow && `drop-${column.dropWhenNarrow}`].filter(Boolean).join(' ') || undefined
}

interface DataTableProps<T> {
  columns: Column<T>[]
  rows: T[] | undefined
  rowKey: (row: T) => string
  /** Phone layout: each row becomes a card instead of a squeezed table row. */
  card: (row: T) => ReactNode
  rowHref?: (row: T) => string
  loading?: boolean
  empty: ReactNode
}

export function DataTable<T>({ columns, rows, rowKey, card, rowHref, loading, empty }: DataTableProps<T>) {
  const isDesktop = useIsDesktop()
  const navigate = useNavigate()
  if (loading || !rows) return <LoadingState />
  if (rows.length === 0) return <>{empty}</>

  if (!isDesktop) {
    return (
      <div className="record-list">
        {rows.map((row) =>
          rowHref ? (
            <a key={rowKey(row)} className="record-card" href={rowHref(row)}
               onClick={(event) => { event.preventDefault(); navigate(rowHref(row)) }}>
              {card(row)}
            </a>
          ) : (
            <div key={rowKey(row)} className="record-card">{card(row)}</div>
          ),
        )}
      </div>
    )
  }
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.header} className={cellClass(column)} style={{ width: column.width }}>{column.header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)} className={rowHref ? 'clickable' : undefined}
                onClick={rowHref ? (event) => {
                  // Let buttons and links inside the row do their own thing.
                  if (!(event.target as HTMLElement).closest('button, a, select, input')) navigate(rowHref(row))
                } : undefined}>
              {columns.map((column) => (
                <td key={column.header} className={cellClass(column)}>{column.render(row)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Pagination({ page, pageSize, count, onChange }: {
  page: number
  pageSize: number
  count: number
  onChange: (page: number) => void
}) {
  const pages = Math.max(1, Math.ceil(count / pageSize))
  if (count <= pageSize) return null
  const from = (page - 1) * pageSize + 1
  return (
    <nav className="pagination" aria-label="Pagination">
      <span>{from}–{Math.min(page * pageSize, count)} of {count}</span>
      <div className="row">
        <Button size="sm" icon={<ChevronLeft size={16} />} disabled={page <= 1} onClick={() => onChange(page - 1)}>Previous</Button>
        <Button size="sm" disabled={page >= pages} onClick={() => onChange(page + 1)}>Next<ChevronRight size={16} /></Button>
      </div>
    </nav>
  )
}

interface FileUploadProps {
  onFiles: (files: File[]) => void
  busy?: boolean
  maxMb: number
}

/** Drop area on desktop; on phones the button opens the camera or file picker. */
export function FileUpload({ onFiles, busy, maxMb }: FileUploadProps) {
  const input = useRef<HTMLInputElement>(null)
  const [active, setActive] = useState(false)
  return (
    <div
      className="dropzone"
      data-active={active}
      onDragOver={(event) => { event.preventDefault(); setActive(true) }}
      onDragLeave={() => setActive(false)}
      onDrop={(event) => {
        event.preventDefault()
        setActive(false)
        onFiles(Array.from(event.dataTransfer.files))
      }}
    >
      <Upload size={20} />
      <span className="desktop-only">Drag files here, or</span>
      <Button variant="secondary" icon={<Paperclip size={16} />} loading={busy} onClick={() => input.current?.click()}>
        Choose files
      </Button>
      <span className="xs muted">PDF, images, Word, Excel or CSV · up to {maxMb} MB each</span>
      <input
        ref={input}
        type="file"
        multiple
        hidden
        accept=".pdf,.png,.jpg,.jpeg,.webp,.doc,.docx,.xls,.xlsx,.csv,.txt"
        onChange={(event) => {
          onFiles(Array.from(event.target.files ?? []))
          event.target.value = ''
        }}
      />
    </div>
  )
}

export function AttachmentList({ attachments, onOpen, onDownload, onRemove }: {
  attachments: Attachment[]
  onOpen: (attachment: Attachment) => void
  onDownload: (attachment: Attachment) => void
  onRemove?: (attachment: Attachment) => void
}) {
  if (attachments.length === 0) {
    return <EmptyState icon={<Paperclip size={20} />} title="No documents attached" />
  }
  return (
    <div>
      {attachments.map((file) => (
        <div key={file.id} className="file-row">
          <span className="file-icon">
            {file.content_type.startsWith('image/') ? <ImageIcon size={18} /> : <FileText size={18} />}
          </span>
          <div className="grow">
            <button
              type="button"
              className="strong small truncate"
              style={{ border: 0, background: 'none', padding: 0, color: 'var(--accent)', maxWidth: '100%', display: 'block' }}
              onClick={() => (file.previewable ? onOpen(file) : onDownload(file))}
            >
              {file.original_name}
            </button>
            <div className="xs muted">
              {file.kind_display} · {fileSize(file.size)} · {file.uploaded_by_name} · {formatDate(file.created_at)}
            </div>
          </div>
          <Button size="sm" variant="ghost" onClick={() => onDownload(file)}>Download</Button>
          {onRemove && file.can_delete && (
            <button type="button" className="icon-btn" aria-label={`Remove ${file.original_name}`} onClick={() => onRemove(file)}>
              <Trash2 size={16} />
            </button>
          )}
        </div>
      ))}
    </div>
  )
}
