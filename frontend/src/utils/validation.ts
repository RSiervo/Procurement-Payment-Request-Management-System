import type { FormKind, RequestLine } from '../types'
import { todayIso } from './format'

/** Client-side checks that mirror the server's submission rules. The server remains the authority. */

export interface DraftForm {
  typeCode: string
  formKind: FormKind
  department: string
  priority: string
  purpose: string
  dateNeeded: string
  payableTo: string
  /** Who the request is for. Null means the signed-in person. */
  requesterId: string | null
  requesterName: string
  sourceRequest: string | null
  prReference: string
  poNumber: string
  rrNumber: string
  invoiceNumber: string
  posted: boolean | null
  lines: RequestLine[]
}

export type FieldErrors = Record<string, string>

export function emptyLine(): RequestLine {
  return { description: '', remarks: '', quantity: '', unit_cost: '', amount: '', expense_date: '', category: '' }
}

export function lineAmount(kind: FormKind, line: RequestLine): number {
  if (kind === 'ITEMS') return (Number(line.quantity) || 0) * (Number(line.unit_cost) || 0)
  return Number(line.amount) || 0
}

export function totalAmount(kind: FormKind, lines: RequestLine[]): number {
  return lines.reduce((sum, line) => sum + lineAmount(kind, line), 0)
}

export function validateDetails(form: DraftForm): FieldErrors {
  const errors: FieldErrors = {}
  if (!form.department) errors.department = 'Department is required.'
  if (form.typeCode === 'PR') {
    if (!form.dateNeeded) errors.dateNeeded = 'Date Needed is required.'
    else if (form.dateNeeded < todayIso()) errors.dateNeeded = 'Date Needed cannot be in the past.'
  }
  if (form.formKind !== 'ITEMS' && !form.payableTo.trim()) errors.payableTo = 'Payable To is required.'
  if (form.typeCode === 'LIQ' && !form.sourceRequest) errors.sourceRequest = 'Choose the cash advance this liquidation accounts for.'
  if (form.formKind === 'EXPENSE' && !form.purpose.trim()) {
    errors.purpose = 'Purpose / Business Justification is required.'
  }
  return errors
}

/** Returns one error map per line (same order), plus a `_form` message when there are no lines. */
export function validateLines(form: DraftForm): { lines: FieldErrors[]; form?: string } {
  if (form.lines.length === 0) return { lines: [], form: 'At least one item is required.' }
  const today = todayIso()
  const lines = form.lines.map((line) => {
    const errors: FieldErrors = {}
    if (!line.description.trim()) errors.description = 'Description is required.'
    if (form.formKind === 'ITEMS') {
      if (!(Number(line.quantity) > 0)) errors.quantity = 'Quantity must be greater than zero.'
      if (line.unit_cost !== '' && line.unit_cost != null && Number(line.unit_cost) < 0) {
        errors.unit_cost = 'Cost cannot be negative.'
      }
    } else if (!(Number(line.amount) > 0)) {
      errors.amount = 'Amount must be greater than zero.'
    }
    if (form.formKind === 'EXPENSE') {
      if (!line.expense_date) errors.expense_date = 'Expense date is required.'
      else if (line.expense_date > today) errors.expense_date = 'Expense date cannot be in the future.'
      if (!line.category) errors.category = 'Category is required.'
    }
    return errors
  })
  return { lines }
}

export function hasErrors(errors: FieldErrors | FieldErrors[]): boolean {
  return Array.isArray(errors) ? errors.some((e) => Object.keys(e).length > 0) : Object.keys(errors).length > 0
}
