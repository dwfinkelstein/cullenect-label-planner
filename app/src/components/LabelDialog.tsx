import { useRef, useState } from 'react'
import { useDialog } from '../useDialog'
import { TextBlockFields } from './Editor'
import { FastenerPicker, HardwarePicker } from './IconPicker'
import { FitWarning } from './FitWarning'
import { TagInput } from './TagInput'
import { Preview } from './Preview'
import type { Label, Meta } from '../types'
import { emptyLabel, labelTitle } from '../types'

const field = 'w-full rounded-md border border-slate-700 bg-slate-800 px-2 py-1.5 text-sm text-slate-100 focus:border-emerald-500 focus:outline-none'
const cap = 'block text-[11px] font-medium uppercase tracking-wide text-slate-400'

const metricLengths = {
  M2: '4 5 6 8 10 12 16 20',
  'M2.5': '4 5 6 8 10 12 16 20 25',
  M3: '4 5 6 8 10 12 14 16 18 20 25 30 35 40',
  'M3.5': '6 8 10 12 16 20 25 30',
  M4: '6 8 10 12 14 16 18 20 25 30 35 40 45 50',
  M5: '8 10 12 14 16 18 20 25 30 35 40 45 50 55 60',
}
const saeLengths = {
  '1/4': '1/4 3/8 1/2 5/8 3/4 7/8 1 1-1/4 1-1/2 1-3/4 2 2-1/4 2-1/2',
  '5/16': '3/8 1/2 5/8 3/4 7/8 1 1-1/4 1-1/2 1-3/4 2 2-1/4 2-1/2',
  '3/8': '1/2 5/8 3/4 7/8 1 1-1/4 1-1/2 1-3/4 2 2-1/4 2-1/2',
  '7/16': '3/4 1 1-1/4 1-1/2 1-3/4 2 2-1/2',
  '1/2': '3/4 1 1-1/4 1-1/2 1-3/4 2 2-1/4 2-1/2',
}
const sizeOptions = Object.entries({ ...metricLengths, ...saeLengths }).map(([size, lengths]) => ({
  size,
  lengths: lengths.split(' '),
  unit: size.startsWith('M') ? 'mm' : '″',
  prefix: new RegExp(`^\\s*${size.replace('.', '\\.')}(?=\\s|[x×"″-]|$)`, 'i'),
}))

// Handle compact labels and retain optional thread pitch, inch marks, and descriptions.
const lengthPattern = /^\s*[x×]\s*((?:\d+[- ]+)?\d+\/\d+|\d+(?:\.\d+)?)(?:\s*(?:mm|["″]))?(?=\s|$)/i

function parseFastenerText(text: string) {
  const preset = sizeOptions.find(({ prefix }) => prefix.test(text))
  const diameter = preset ? text.match(preset.prefix)?.[0] ?? '' : ''
  const remainder = text.slice(diameter.length)
  const thread = remainder.match(/^["″]?(?:-\d+(?:\.\d+)?)?/)?.[0] ?? ''
  const prefix = diameter + thread
  const suffix = text.slice(prefix.length)
  const length = suffix.match(lengthPattern)
  return { preset, prefix, suffix, length }
}

function lengthInches(length: string) {
  const parts = length.replace('-', ' ').split(' ')
  return parts.reduce((total, part) => {
    const [numerator, denominator] = part.split('/').map(Number)
    return total + (denominator ? numerator / denominator : numerator)
  }, 0)
}

function matchingLength(preset: (typeof sizeOptions)[number] | undefined, length: string) {
  const numeric = preset?.unit === '″' ? lengthInches : Number
  return preset?.lengths.find((option) => numeric(option) === numeric(length)) ?? ''
}

/**
 * One dialog for creating AND editing a label. It replaced the permanent side panel: a
 * single editing surface means one place to keep correct, and nothing that can be pushed
 * off-screen at an awkward viewport — which is how the editor became unreachable twice.
 */
export function LabelDialog({ mode, initial, meta, knownTags = [], onCancel, onSubmit, onDelete }: {
  mode: 'create' | 'edit'
  initial?: Label
  meta: Meta | null
  knownTags?: string[]
  onCancel: () => void
  onSubmit: (label: Label) => Promise<void> | void
  onDelete?: (label: Label) => Promise<void> | void
}) {
  const [label, setLabel] = useState<Label>(() =>
    initial ? structuredClone(initial) : { ...emptyLabel(), name: '' })
  const dialogRef = useRef<HTMLDivElement>(null)
  useDialog(dialogRef, onCancel)
  const [busy, setBusy] = useState(false)
  const [advanced, setAdvanced] = useState(false)

  const set = <K extends keyof Label>(k: K, v: Label[K]) => setLabel((l) => ({ ...l, [k]: v }))
  const dimensions = parseFastenerText(label.text1.text)
  const sizePreset = dimensions.preset
  const lengthPreset = dimensions.length ? matchingLength(sizePreset, dimensions.length[1]) : ''
  const setSizePreset = (size: string) => {
    setLabel((current) => {
      const { text } = current.text1
      const { preset, prefix, suffix, length } = parseFastenerText(text)
      const nextPreset = sizeOptions.find((option) => option.size === size)
      const compatible = !length || (preset?.unit === nextPreset?.unit
        && (!matchingLength(preset, length[1]) || matchingLength(nextPreset, length[1])))
      const next = preset
        ? prefix.replace(preset.prefix, size) + (compatible ? suffix : suffix.slice(length?.[0].length ?? 0))
        : [size, text.trimStart()].filter(Boolean).join(' ')
      return { ...current, text1: { ...current.text1, text: next } }
    })
  }
  const setLengthPreset = (length: string) => {
    setLabel((current) => {
      const { preset, prefix, suffix, length: previous } = parseFastenerText(current.text1.text)
      if (!preset) return current
      const text = `${prefix} × ${length}${preset.unit === '″' ? '″' : ''}${suffix.slice(previous?.[0].length ?? 0)}`
      return { ...current, text1: { ...current.text1, text } }
    })
  }
  const dirty = !initial || JSON.stringify(label) !== JSON.stringify(initial)


  const submit = async () => {
    setBusy(true)
    try {
      await onSubmit({
        ...label,
        name: label.name.trim() || label.text1.text.trim() || 'Untitled label',
      })
    } finally { setBusy(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-950/80 p-4"
         role="dialog" aria-modal="true" aria-label={mode === 'create' ? 'New label' : 'Edit label'}
         onMouseDown={(e) => { if (e.target === e.currentTarget) onCancel() }}>
      <div ref={dialogRef} className="my-auto w-full max-w-4xl rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl">
        <header className="flex items-center justify-between border-b border-slate-800 px-5 py-3">
          <h2 className="text-base font-semibold text-slate-100">
            {mode === 'create' ? 'New label' : `Edit · ${labelTitle(label)}`}
          </h2>
          <button className="text-slate-400 hover:text-slate-100" onClick={onCancel} aria-label="Close">✕</button>
        </header>

        <div className="grid gap-5 p-5 md:grid-cols-[1fr_18rem]">
          <div className="space-y-5">
            <section className="space-y-2">
              <h3 className="text-sm font-semibold text-slate-200">1 · What does it say?</h3>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className={cap} htmlFor="nl-size-preset">Fastener size (optional)</label>
                  <select id="nl-size-preset" className={field} value={sizePreset?.size ?? ''}
                          onChange={(e) => setSizePreset(e.target.value)}>
                    <option value="" disabled>Choose a size</option>
                    <optgroup label="Metric">
                      {Object.keys(metricLengths).map((size) => <option key={size}>{size}</option>)}
                    </optgroup>
                    <optgroup label="SAE (inches)">
                      {Object.keys(saeLengths).map((size) => <option key={size}>{size}</option>)}
                    </optgroup>
                  </select>
                </div>
                <div>
                  <label className={cap} htmlFor="nl-length-preset">Length (optional)</label>
                  <select id="nl-length-preset" className={`${field} disabled:opacity-50`}
                          value={lengthPreset} disabled={!sizePreset}
                          onChange={(e) => setLengthPreset(e.target.value)}>
                    <option value="" disabled>{sizePreset ? 'Choose a length' : 'Choose a size first'}</option>
                    {sizePreset?.lengths.map((length) => (
                      <option key={length} value={length}>
                        {length}{sizePreset.unit === 'mm' ? ' mm' : '″'}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                <div>
                  <label className={cap} htmlFor="nl-t1">Text</label>
                  <input id="nl-t1" autoFocus className={field} placeholder="M3 x 12"
                         value={label.text1.text}
                         onChange={(e) => set('text1', { ...label.text1, text: e.target.value })} />
                </div>
                <div>
                  <label className={cap} htmlFor="nl-t2">Second text (optional)</label>
                  <input id="nl-t2" className={field} placeholder="right-aligned"
                         value={label.text2.text}
                         onChange={(e) => set('text2', { ...label.text2, text: e.target.value })} />
                </div>
              </div>
              <div className="grid gap-2 sm:grid-cols-3">
                <div>
                  <label className={cap} htmlFor="nl-w">Width (Gridfinity U)</label>
                  <input id="nl-w" className={field} type="number" step="0.1" min="0.1" max="8"
                         value={label.width_u}
                         onChange={(e) => set('width_u', Number(e.target.value))} />
                </div>
                <div>
                  <label className={cap} htmlFor="nl-qty">Qty on plate</label>
                  <input id="nl-qty" className={field} type="number" min="1" max="50"
                         value={label.qty}
                         onChange={(e) => set('qty', Math.max(1, Number(e.target.value)))} />
                </div>
                <div>
                  <label className={cap} htmlFor="nl-name">Library name (optional)</label>
                  <input id="nl-name" className={field} placeholder="defaults to the text"
                         value={label.name} onChange={(e) => set('name', e.target.value)} />
                </div>
              </div>

              <button type="button" onClick={() => setAdvanced((a) => !a)}
                      className="text-xs text-emerald-400 hover:text-emerald-300">
                {advanced ? '− Hide' : '+ Show'} text options (font, alignment, size, nudge)
              </button>
              {advanced && (
                <div className="grid gap-3 rounded-lg border border-slate-800 bg-slate-950/40 p-3 sm:grid-cols-2">
                  <div>
                    <div className="mb-1 text-xs font-semibold text-slate-300">Text 1</div>
                    <TextBlockFields value={label.text1} meta={meta} prefix="t1"
                                     onChange={(v: Label['text1']) => set('text1', v)} />
                  </div>
                  <div>
                    <div className="mb-1 text-xs font-semibold text-slate-300">Text 2</div>
                    <TextBlockFields value={label.text2} meta={meta} prefix="t2"
                                     onChange={(v: Label['text2']) => set('text2', v)} />
                  </div>
                </div>
              )}
            </section>

            <section className="space-y-3">
              <h3 className="text-sm font-semibold text-slate-200">2 · Pick an icon</h3>
              <FastenerPicker value={label.fastener} meta={meta}
                              onChange={(v) => set('fastener', v)} />
              <div className="border-t border-slate-800 pt-3">
                <HardwarePicker value={label.hardware} options={meta?.hardware ?? ['none']}
                                onChange={(v) => set('hardware', v)} />
              </div>
            </section>
          </div>

          <aside className="space-y-3">
            <h3 className="text-sm font-semibold text-slate-200">Preview</h3>
            <div className="h-56"><Preview label={label} /></div>
            <FitWarning label={label} onApply={(patch) => setLabel((l) => ({ ...l, ...patch }))} />
            <div className="space-y-2">
              <div>
                <label className={cap} htmlFor="nl-surface">Surface</label>
                <select id="nl-surface" className={field} value={label.surface}
                        onChange={(e) => set('surface', e.target.value as Label['surface'])}>
                  <option value="emboss">Emboss (raised)</option>
                  <option value="deboss">Deboss (recessed)</option>
                  <option value="flush">Flush (3MF colour swap)</option>
                </select>
              </div>
              <div>
                <label className={cap} htmlFor="nl-color">Text colour</label>
                <div className="flex gap-2">
                  <input id="nl-color" type="color"
                         className="h-[34px] w-12 rounded-md border border-slate-700 bg-slate-800"
                         value={label.text_color}
                         onChange={(e) => set('text_color', e.target.value)} />
                  <input className={field} value={label.text_color}
                         onChange={(e) => set('text_color', e.target.value)} />
                </div>
              </div>
              <div>
                <label className={cap} htmlFor="tag-input">Tags</label>
                <TagInput value={label.tags} suggestions={knownTags}
                          onChange={(t) => set('tags', t)} />
              </div>
              <label className="flex items-center gap-2 text-sm text-slate-300">
                <input type="checkbox" checked={label.backward_compatible}
                       onChange={(e) => set('backward_compatible', e.target.checked)} />
                V1-compatible latches
              </label>
            </div>
          </aside>
        </div>

        <footer className="flex items-center justify-between gap-3 border-t border-slate-800 px-5 py-3">
          {mode === 'edit' && onDelete ? (
            <button className="rounded-md border border-red-900/60 px-3 py-1.5 text-sm text-red-400 hover:border-red-500 hover:text-red-300"
                    onClick={() => onDelete(label)}>Delete</button>
          ) : (
            <p className="text-xs text-slate-500">Everything here stays editable afterwards.</p>
          )}
          <div className="flex gap-2">
            <button className="rounded-md border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 hover:border-slate-500"
                    onClick={onCancel}>Cancel</button>
            <button className="rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-40"
                    disabled={busy || (mode === 'edit' && !dirty)} onClick={submit}>
              {busy ? 'Saving…' : mode === 'create' ? 'Add label' : 'Save changes'}
            </button>
          </div>
        </footer>
      </div>
    </div>
  )
}
