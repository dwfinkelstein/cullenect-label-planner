import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { FastenerPicker, HardwarePicker } from './IconPicker'
import { TagInput } from './TagInput'
import type { Label, Meta } from '../types'
import { emptyLabel } from '../types'

const field = 'w-full rounded-md border border-slate-700 bg-slate-800 px-2 py-1.5 text-sm text-slate-100 focus:border-emerald-500 focus:outline-none'
const cap = 'block text-[11px] font-medium uppercase tracking-wide text-slate-400'

const SAMPLE = `M3 x 8
M3 x 12
M3 x 16
M4 x 12 | 20 pcs
# lines starting with # are ignored`

/**
 * Paste a list, get a batch. A label library usually starts from a list you already have
 * — a drawer inventory, a BOM, a spreadsheet column — and retyping it one dialog at a
 * time is the actual cost. The shared settings are chosen once and applied to every line.
 */
export function BulkPasteDialog({ meta, knownTags = [], onCancel, onDone }: {
  meta: Meta | null
  knownTags?: string[]
  onCancel: () => void
  onDone: (created: Label[]) => void
}) {
  const [text, setText] = useState('')
  const [template, setTemplate] = useState<Label>(() => emptyLabel())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const set = <K extends keyof Label>(k: K, v: Label[K]) =>
    setTemplate((t) => ({ ...t, [k]: v }))

  // Parsed client-side purely for the live count/preview; the server re-parses on submit
  // with the same rules, so the two can't disagree about what gets created.
  const parsed = useMemo(() => {
    return text.split('\n').map((l) => l.trim())
      .filter((l) => l && !l.startsWith('#'))
      .map((l) => {
        const sep = l.includes('|') ? '|' : l.includes('\t') ? '\t' : ''
        if (!sep) return { first: l, second: '' }
        const [a, ...rest] = l.split(sep)
        return { first: a.trim(), second: rest.join(sep).trim() }
      })
  }, [text])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onCancel() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onCancel])

  const submit = async () => {
    setBusy(true)
    setError('')
    try {
      const created = await api.bulkCreate(text, template)
      onDone(created)
    } catch (e) {
      setError((e as Error).message)
    } finally { setBusy(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-950/80 p-4"
         role="dialog" aria-modal="true" aria-label="Paste a list"
         onMouseDown={(e) => { if (e.target === e.currentTarget) onCancel() }}>
      <div className="my-auto w-full max-w-4xl rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl">
        <header className="flex items-center justify-between border-b border-slate-800 px-5 py-3">
          <h2 className="text-base font-semibold text-slate-100">Paste a list</h2>
          <button className="text-slate-400 hover:text-slate-100" onClick={onCancel} aria-label="Close">✕</button>
        </header>

        <div className="grid gap-5 p-5 md:grid-cols-[1fr_16rem]">
          <div className="space-y-4">
            <section className="space-y-1.5">
              <h3 className="text-sm font-semibold text-slate-200">1 · One label per line</h3>
              <p className="text-xs text-slate-500">
                Use <code className="text-slate-400">|</code> or a tab to add second text
                (so a two-column spreadsheet paste works). <code className="text-slate-400">#</code> comments and blank lines are skipped.
              </p>
              <textarea
                id="bulk-text"
                autoFocus
                spellCheck={false}
                className={`${field} h-64 resize-y font-mono text-[13px] leading-relaxed`}
                placeholder={SAMPLE}
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
            </section>

            <section className="space-y-3">
              <h3 className="text-sm font-semibold text-slate-200">
                2 · Settings applied to all {parsed.length || ''}
              </h3>
              <FastenerPicker value={template.fastener} meta={meta}
                              onChange={(v) => set('fastener', v)} />
              <div className="border-t border-slate-800 pt-3">
                <HardwarePicker value={template.hardware} options={meta?.hardware ?? ['none']}
                                onChange={(v) => set('hardware', v)} />
              </div>
            </section>
          </div>

          <aside className="space-y-3">
            <h3 className="text-sm font-semibold text-slate-200">
              {parsed.length} label{parsed.length === 1 ? '' : 's'}
            </h3>
            <ul className="max-h-56 space-y-1 overflow-y-auto rounded-lg border border-slate-800 bg-slate-950/50 p-2 text-xs">
              {parsed.slice(0, 60).map((p, i) => (
                <li key={i} className="flex justify-between gap-2 text-slate-300">
                  <span className="truncate">{p.first}</span>
                  {p.second && <span className="shrink-0 text-slate-500">{p.second}</span>}
                </li>
              ))}
              {!parsed.length && <li className="text-slate-600">Nothing pasted yet.</li>}
              {parsed.length > 60 && (
                <li className="text-slate-500">… and {parsed.length - 60} more</li>
              )}
            </ul>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className={cap} htmlFor="bulk-width">Width (U)</label>
                <input id="bulk-width" className={field} type="number" step="0.1" min="0.1" max="8"
                       value={template.width_u}
                       onChange={(e) => set('width_u', Number(e.target.value))} />
              </div>
              <div>
                <label className={cap} htmlFor="bulk-qty">Qty each</label>
                <input id="bulk-qty" className={field} type="number" min="1" max="50"
                       value={template.qty}
                       onChange={(e) => set('qty', Math.max(1, Number(e.target.value)))} />
              </div>
              <div className="col-span-2">
                <label className={cap} htmlFor="bulk-surface">Surface</label>
                <select id="bulk-surface" className={field} value={template.surface}
                        onChange={(e) => set('surface', e.target.value as Label['surface'])}>
                  <option value="emboss">Emboss (raised)</option>
                  <option value="deboss">Deboss (recessed)</option>
                  <option value="flush">Flush (3MF colour swap)</option>
                </select>
              </div>
              <div className="col-span-2">
                <label className={cap} htmlFor="tag-input">Tags for the whole batch</label>
                <TagInput value={template.tags} suggestions={knownTags}
                          onChange={(t) => set('tags', t)} />
              </div>
              <div className="col-span-2">
                <label className={cap} htmlFor="bulk-color">Text colour</label>
                <div className="flex gap-2">
                  <input id="bulk-color" type="color"
                         className="h-[34px] w-12 rounded-md border border-slate-700 bg-slate-800"
                         value={template.text_color}
                         onChange={(e) => set('text_color', e.target.value)} />
                  <input className={field} value={template.text_color}
                         onChange={(e) => set('text_color', e.target.value)} />
                </div>
              </div>
            </div>
          </aside>
        </div>

        <footer className="flex items-center justify-between gap-3 border-t border-slate-800 px-5 py-3">
          <p className="text-xs text-red-400">{error}</p>
          <div className="flex gap-2">
            <button className="rounded-md border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 hover:border-slate-500"
                    onClick={onCancel}>Cancel</button>
            <button className="rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-40"
                    disabled={busy || !parsed.length} onClick={submit}>
              {busy ? 'Adding…' : `Add ${parsed.length || ''} label${parsed.length === 1 ? '' : 's'}`}
            </button>
          </div>
        </footer>
      </div>
    </div>
  )
}
