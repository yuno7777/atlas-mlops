import {
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import { Icon, type IconName } from './Icon'
import { useToast } from './ToastProvider'
import type { PillTone } from '../lib/format'
import { formatNumber } from '../lib/format'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'danger-ghost'
type Size = 'sm' | 'md'

export function buttonClass(variant: Variant = 'secondary', size: Size = 'md'): string {
  return `btn btn-${variant} btn-${size}`
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  loading?: boolean
  icon?: IconName
}

export function Button({
  variant = 'secondary',
  size = 'md',
  loading,
  icon,
  children,
  className = '',
  disabled,
  ...props
}: ButtonProps) {
  return (
    <button
      type="button"
      className={`${buttonClass(variant, size)} ${className}`}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? <span className="spinner" aria-hidden="true" /> : icon ? <Icon name={icon} /> : null}
      {children}
    </button>
  )
}

interface LinkButtonProps {
  to: string
  variant?: Variant
  size?: Size
  icon?: IconName
  children: ReactNode
  className?: string
}

export function LinkButton({
  to,
  variant = 'secondary',
  size = 'md',
  icon,
  children,
  className = '',
}: LinkButtonProps) {
  return (
    <Link to={to} className={`${buttonClass(variant, size)} ${className}`}>
      {icon ? <Icon name={icon} /> : null}
      {children}
    </Link>
  )
}

interface FieldProps {
  label: ReactNode
  htmlFor?: string
  hint?: ReactNode
  error?: string | null
  children: ReactNode
  className?: string
}

export function Field({ label, htmlFor, hint, error, children, className = '' }: FieldProps) {
  return (
    <div className={`field ${className}`}>
      <label className="field-label" htmlFor={htmlFor}>
        {label}
      </label>
      {children}
      {error ? <p className="field-error">{error}</p> : hint ? <p className="field-hint">{hint}</p> : null}
    </div>
  )
}

export function Input({ className = '', ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={`input ${className}`} {...props} />
}

export function Textarea({ className = '', ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={`input textarea ${className}`} {...props} />
}

export function Select({ className = '', children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className={`select-wrap ${className}`}>
      <select className="input select" {...props}>
        {children}
      </select>
      <Icon name="chevron-down" size={14} className="select-chevron" />
    </div>
  )
}

interface SearchInputProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  ariaLabel?: string
}

export function SearchInput({ value, onChange, placeholder = 'Search', ariaLabel }: SearchInputProps) {
  return (
    <div className="search-input">
      <Icon name="search" size={15} className="search-icon" />
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        aria-label={ariaLabel ?? placeholder}
      />
    </div>
  )
}

export function Checkbox({
  label,
  checked,
  onChange,
  disabled,
}: {
  label: ReactNode
  checked: boolean
  onChange: (checked: boolean) => void
  disabled?: boolean
}) {
  return (
    <label className={`checkbox ${disabled ? 'is-disabled' : ''}`}>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span>{label}</span>
    </label>
  )
}

export function Toggle({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean
  onChange: (checked: boolean) => void
  label: string
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      className={`toggle ${checked ? 'is-on' : ''}`}
      disabled={disabled}
      onClick={() => onChange(!checked)}
    >
      <span className="toggle-knob" />
    </button>
  )
}

const tones: PillTone[] = ['positive', 'negative', 'warning', 'info', 'neutral']

export function Pill({
  children,
  tone = 'neutral',
  dot = false,
}: {
  children: ReactNode
  tone?: PillTone
  dot?: boolean
}) {
  const safeTone = tones.includes(tone) ? tone : 'neutral'
  return (
    <span className={`pill pill-${safeTone}`}>
      {dot ? <span className="pill-dot" /> : null}
      {children}
    </span>
  )
}

export function StatusPill({
  status,
  label,
  tone,
  dot = true,
}: {
  status: string
  label?: string
  tone?: PillTone
  dot?: boolean
}) {
  return (
    <Pill tone={tone ?? 'neutral'} dot={dot}>
      {label ?? status}
    </Pill>
  )
}

interface PageHeaderProps {
  title: string
  eyebrow?: ReactNode
  breadcrumbs?: { label: string; to?: string }[]
  description?: ReactNode
  actions?: ReactNode
  backTo?: string
  backLabel?: string
}

export function PageHeader({
  title,
  eyebrow,
  breadcrumbs,
  description,
  actions,
  backTo,
  backLabel = 'Back',
}: PageHeaderProps) {
  return (
    <header className="page-header">
      <div className="page-header-main">
        {breadcrumbs ? (
          <nav className="breadcrumbs" aria-label="Breadcrumbs">
            {breadcrumbs.map((crumb, idx) => (
              <span key={idx} className="breadcrumb-item">
                {idx > 0 ? <span className="breadcrumb-sep">/</span> : null}
                {crumb.to ? (
                  <Link to={crumb.to} className="breadcrumb-link">
                    {crumb.label}
                  </Link>
                ) : (
                  <span>{crumb.label}</span>
                )}
              </span>
            ))}
          </nav>
        ) : backTo ? (
          <Link to={backTo} className="back-link">
            <Icon name="arrow-left" size={14} />
            {backLabel}
          </Link>
        ) : null}
        {eyebrow ? <div className="eyebrow">{eyebrow}</div> : null}
        <h1>{title}</h1>
        {description ? <div className="page-description">{description}</div> : null}
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </header>
  )
}

export function SectionHeader({
  title,
  description,
  action,
}: {
  title: ReactNode
  description?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="section-header">
      <div>
        <h2>{title}</h2>
        {description ? <p className="section-description">{description}</p> : null}
      </div>
      {action ? <div className="section-action">{action}</div> : null}
    </div>
  )
}

export function Panel({
  children,
  className = '',
  as: Tag = 'section',
}: {
  children: ReactNode
  className?: string
  as?: 'section' | 'div'
}) {
  return <Tag className={`panel ${className}`}>{children}</Tag>
}

export interface KpiItem {
  label: string
  value: ReactNode
  sub?: ReactNode
  tone?: 'positive' | 'negative' | 'muted'
}

export function KpiStrip({ items }: { items: KpiItem[] }) {
  return (
    <div className={`kpi-strip kpi-count-${items.length}`}>
      {items.map((item) => (
        <div className="kpi" key={item.label}>
          <span className="kpi-label">{item.label}</span>
          <span className="kpi-value num">{item.value}</span>
          {item.sub ? <span className={`kpi-sub ${item.tone ? `kpi-sub-${item.tone}` : ''}`}>{item.sub}</span> : null}
        </div>
      ))}
    </div>
  )
}

export interface TabItem {
  id: string
  label: string
  count?: number
}

export function Tabs({
  items,
  value,
  onChange,
  ariaLabel = 'Sections',
}: {
  items: TabItem[]
  value: string
  onChange: (id: string) => void
  ariaLabel?: string
}) {
  return (
    <div className="tabs" role="tablist" aria-label={ariaLabel}>
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          role="tab"
          aria-selected={value === item.id}
          className={`tab ${value === item.id ? 'is-active' : ''}`}
          onClick={() => onChange(item.id)}
        >
          {item.label}
          {item.count !== undefined ? <span className="tab-count num">{item.count}</span> : null}
        </button>
      ))}
    </div>
  )
}

export function EmptyState({
  title,
  description,
  icon = 'layers',
  action,
  compact,
}: {
  title: string
  description: ReactNode
  icon?: IconName
  action?: ReactNode
  compact?: boolean
}) {
  return (
    <div className={`empty-state ${compact ? 'is-compact' : ''}`}>
      <Icon name={icon} size={20} />
      <div>
        <h3>{title}</h3>
        <p>{description}</p>
      </div>
      {action ? <div className="empty-action">{action}</div> : null}
    </div>
  )
}

export function LoadingBlock({ rows = 4, title }: { rows?: number; title?: string }) {
  return (
    <div className="loading-block" aria-busy="true" aria-label={title ?? 'Loading'}>
      {title ? <span className="sr-only">{title}</span> : null}
      {Array.from({ length: rows }, (_, index) => (
        <div className="skeleton-row" key={index}>
          <span className="skeleton skeleton-label" />
          <span className="skeleton skeleton-value" style={{ width: `${52 - index * 6}%` }} />
        </div>
      ))}
    </div>
  )
}

export function ErrorBlock({
  message,
  onRetry,
  compact,
}: {
  message: string
  onRetry?: () => void
  compact?: boolean
}) {
  return (
    <div className={`error-block ${compact ? 'is-compact' : ''}`} role="alert">
      <Icon name="alert" size={16} />
      <span>{message}</span>
      {onRetry ? (
        <button type="button" className="text-button" onClick={onRetry}>
          Retry
        </button>
      ) : null}
    </div>
  )
}

export function InlineNotice({
  tone = 'info',
  title,
  children,
}: {
  tone?: 'info' | 'warning' | 'negative'
  title?: ReactNode
  children: ReactNode
}) {
  return (
    <div className={`inline-notice notice-${tone}`}>
      <Icon name={tone === 'info' ? 'info' : 'alert'} size={15} />
      <div>
        {title ? <strong>{title}</strong> : null}
        <div>{children}</div>
      </div>
    </div>
  )
}

export function Pagination({
  page,
  pages,
  total,
  pageSize,
  onChange,
}: {
  page: number
  pages: number
  total: number
  pageSize: number
  onChange: (page: number) => void
}) {
  if (total === 0) return null
  const start = (page - 1) * pageSize + 1
  const end = Math.min(total, page * pageSize)
  return (
    <div className="pagination">
      <span className="pagination-range num">
        {formatNumber(start)}–{formatNumber(end)} of {formatNumber(total)}
      </span>
      <div className="pagination-controls">
        <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => onChange(page - 1)}>
          Previous
        </Button>
        <span className="pagination-page num">
          {page} / {Math.max(1, pages)}
        </span>
        <Button
          size="sm"
          variant="secondary"
          disabled={page >= Math.max(1, pages)}
          onClick={() => onChange(page + 1)}
        >
          Next
        </Button>
      </div>
    </div>
  )
}

export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  width = 520,
}: {
  open: boolean
  onClose: () => void
  title: string
  description?: ReactNode
  children: ReactNode
  footer?: ReactNode
  width?: number
}) {
  const titleId = useId()
  const descriptionId = useId()
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKey)
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const timer = window.setTimeout(() => {
      const focusable = panelRef.current?.querySelector<HTMLElement>(
        'input, textarea, select, button:not([data-modal-close])',
      )
      focusable?.focus()
    }, 40)
    return () => {
      document.removeEventListener('keydown', handleKey)
      document.body.style.overflow = previousOverflow
      window.clearTimeout(timer)
    }
  }, [open, onClose])

  if (!open) return null
  return createPortal(
    <div className="modal-overlay" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div
        className="modal-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        style={{ maxWidth: width }}
        ref={panelRef}
      >
        <div className="modal-head">
          <div>
            <h2 id={titleId}>{title}</h2>
            {description ? <p id={descriptionId}>{description}</p> : null}
          </div>
          <button
            type="button"
            className="icon-button"
            onClick={onClose}
            aria-label="Close dialog"
            data-modal-close
          >
            <Icon name="close" size={16} />
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer ? <div className="modal-foot">{footer}</div> : null}
      </div>
    </div>,
    document.body,
  )
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = 'Confirm',
  tone = 'danger',
  pending,
  loading,
  onConfirm,
  onClose,
}: {
  open: boolean
  title: string
  description: ReactNode
  confirmLabel?: string
  tone?: 'danger' | 'primary' | 'warning'
  pending?: boolean
  loading?: boolean
  onConfirm: () => void
  onClose: () => void
}) {
  const isPending = pending ?? loading
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      description={description}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={isPending}>
            Cancel
          </Button>
          <Button
            variant={tone === 'danger' ? 'danger' : 'primary'}
            loading={isPending}
            onClick={onConfirm}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="confirm-spacer" />
    </Modal>
  )
}

export function TableSkeleton({
  columns = 5,
  rows = 6,
}: {
  columns?: number
  rows?: number
}) {
  return (
    <div className="table-wrap" aria-busy="true">
      <table className="data">
        <tbody>
          {Array.from({ length: rows }, (_, r) => (
            <tr key={r}>
              {Array.from({ length: columns }, (_, c) => (
                <td key={c}>
                  <span
                    className="skeleton"
                    style={{
                      width: `${45 + ((r * 19 + c * 29) % 40)}%`,
                      height: 14,
                      display: 'inline-block',
                    }}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Dropdown({
  label,
  align = 'left',
  children,
  className = '',
  chevron = true,
}: {
  label: ReactNode
  align?: 'left' | 'right'
  children: (close: () => void) => ReactNode
  className?: string
  chevron?: boolean
}) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const close = () => setOpen(false)

  useEffect(() => {
    if (!open) return
    const handlePointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', handlePointer)
    document.addEventListener('keydown', handleKey)
    return () => {
      document.removeEventListener('mousedown', handlePointer)
      document.removeEventListener('keydown', handleKey)
    }
  }, [open])

  return (
    <div className={`dropdown ${className}`} ref={rootRef}>
      <button
        type="button"
        className="dropdown-trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {label}
        {chevron ? <Icon name="chevron-down" size={14} /> : null}
      </button>
      {open ? (
        <div className={`dropdown-menu dropdown-${align}`} role="menu">
          {children(close)}
        </div>
      ) : null}
    </div>
  )
}

export function MenuItem({
  icon,
  children,
  onClick,
  danger,
  disabled,
}: {
  icon?: IconName
  children: ReactNode
  onClick: () => void
  danger?: boolean
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      role="menuitem"
      className={`menu-item ${danger ? 'is-danger' : ''}`}
      onClick={onClick}
      disabled={disabled}
    >
      {icon ? <Icon name={icon} size={14} /> : null}
      {children}
    </button>
  )
}

export function CopyButton({
  value,
  label = 'Copy',
  iconOnly,
}: {
  value: string
  label?: string
  iconOnly?: boolean
}) {
  const toast = useToast()
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      toast.success('Copied to clipboard.')
      window.setTimeout(() => setCopied(false), 1800)
    } catch {
      toast.error('Could not copy. Select the value and copy it manually.')
    }
  }
  return (
    <Button
      size="sm"
      variant="secondary"
      icon={copied ? 'check' : 'copy'}
      onClick={copy}
      aria-label={label}
      className={iconOnly ? 'copy-icon' : ''}
    >
      {iconOnly ? null : copied ? 'Copied' : label}
    </Button>
  )
}

export function ApiKeyDialog({
  apiKey,
  open,
  onClose,
  title = 'API key created',
}: {
  apiKey: string
  open: boolean
  onClose: () => void
  title?: string
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      description="Copy this key now. It is shown once and cannot be recovered."
      width={560}
      footer={
        <Button variant="primary" onClick={onClose}>
          I have saved the key
        </Button>
      }
    >
      <div className="secret-field">
        <code>{apiKey}</code>
        <CopyButton value={apiKey} />
      </div>
      <p className="subtle">
        Use it as the <code className="inline-code">X-API-Key</code> header when calling the deployment
        prediction endpoint.
      </p>
    </Modal>
  )
}

export function CodeBlock({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <pre className={`code-block ${className}`}>{children}</pre>
}

export function JsonBlock({ value }: { value: unknown }) {
  return <pre className="code-block json-block">{JSON.stringify(value, null, 2)}</pre>
}

export function MetaList({ items }: { items: { label: string; value: ReactNode }[] }) {
  return (
    <dl className="meta-list">
      {items.map((item) => (
        <div key={item.label}>
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  )
}

export function DefinitionGrid({
  items,
  columns = 2,
}: {
  items: { label: string; value: ReactNode }[]
  columns?: 2 | 3
}) {
  return (
    <dl className={`definition-grid definition-cols-${columns}`}>
      {items.map((item) => (
        <div key={item.label}>
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  )
}

export function ProgressBar({
  value,
  label,
  tone = 'accent',
}: {
  value: number
  label?: string
  tone?: 'accent' | 'positive' | 'negative'
}) {
  const bounded = Math.max(0, Math.min(100, value))
  return (
    <div className="progress" aria-label={label ?? `${bounded}% complete`} role="progressbar" aria-valuenow={bounded} aria-valuemin={0} aria-valuemax={100}>
      <span className={`progress-fill progress-${tone}`} style={{ width: `${bounded}%` }} />
    </div>
  )
}

export function SpinnerLabel({ children }: { children: ReactNode }) {
  return (
    <span className="spinner-label">
      <span className="spinner" aria-hidden="true" />
      {children}
    </span>
  )
}
