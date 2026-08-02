import { useState } from 'react'
import type { Label } from '../types'
import { labelTitle, labelWidthMm } from '../types'

interface Props {
  labels: Label[]
  selectedId: string | null
  dirtyId: string | null
  checked: Set<string>
  onSelect: (id: string) => void
  onOpen: (id: string) => void
  onToggle: (id: string) => void
  onToggleAll: (on: boolean) => void
  onQty: (id: string, qty: number) => void
  onDuplicate: (id: string) => void
  onDelete: (id: string) => void
  onMove: (id: string, dir: -1 | 1) => void
}

export function LabelList(props: Props) {
  const { labels, selectedId, dirtyId, checked } = props
  const [query, setQuery] = useState('')

  const q = query.trim().toLowerCase()
  const visible = q
    ? labels.filter((l) =>
        [l.name, l.text1.text, l.text2.text, l.hardware, ...l.tags].join(' ').toLowerCase().includes(q))
    : labels

  const allChecked = visible.length > 0 && visible.every((l) => checked.has(l.id))

  return (
    <div className="flex h-full flex-col">
      <div className="mb-2 flex items-center gap-2">
        <input
          className="w-full rounded-md border border-slate-700 bg-slate-800 px-2 py-1.5 text-sm text-slate-100 focus:border-emerald-500 focus:outline-none"
          placeholder={`Search ${labels.length} labels…`}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <label className="flex shrink-0 items-center gap-1.5 text-xs text-slate-400" title="Include all on the plate">
          <input type="checkbox" checked={allChecked} onChange={(e) => props.onToggleAll(e.target.checked)} />
          all
        </label>
      </div>

      <ul className="min-h-0 flex-1 space-y-1 overflow-y-auto pr-1">
        {visible.map((l) => {
          const active = l.id === selectedId
          return (
            <li key={l.id}>
              <div
                className={`group flex items-center gap-2 rounded-lg border px-2 py-1.5 ${
                  active ? 'border-emerald-500 bg-emerald-500/10' : 'border-slate-800 bg-slate-900/60 hover:border-slate-600'
                }`}
              >
                <input
                  type="checkbox"
                  checked={checked.has(l.id)}
                  onChange={() => props.onToggle(l.id)}
                  title="Include on the build plate"
                />
                <button className="min-w-0 flex-1 text-left" onClick={() => props.onSelect(l.id)}
                        onDoubleClick={() => props.onOpen(l.id)} title="Click to preview · double-click to edit">
                  <div className="flex items-center gap-1.5">
                    <span className="truncate text-sm text-slate-100">{labelTitle(l)}</span>
                    {dirtyId === l.id && <span className="text-[10px] text-amber-400" title="Unsaved changes">●</span>}
                  </div>
                  <div className="truncate text-[11px] text-slate-500">
                    {l.width_u}U · {labelWidthMm(l).toFixed(0)}mm · {l.surface}
                    {l.fastener.show ? ` · ${l.fastener.head}/${l.fastener.driver}` : ''}
                    {l.hardware !== 'none' ? ` · ${l.hardware.replace(/_/g, ' ')}` : ''}
                  </div>
                </button>
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={l.qty}
                  onChange={(e) => props.onQty(l.id, Math.max(1, Number(e.target.value)))}
                  className="w-12 rounded border border-slate-700 bg-slate-800 px-1 py-0.5 text-center text-xs text-slate-200"
                  title="Copies on the build plate"
                />
                <div className="flex flex-col opacity-0 transition group-hover:opacity-100">
                  <button className="px-1 text-[10px] leading-3 text-slate-400 hover:text-slate-100"
                          onClick={() => props.onMove(l.id, -1)} title="Move up">▲</button>
                  <button className="px-1 text-[10px] leading-3 text-slate-400 hover:text-slate-100"
                          onClick={() => props.onMove(l.id, 1)} title="Move down">▼</button>
                </div>
                <button className="px-1 text-xs text-slate-400 opacity-0 transition hover:text-emerald-300 group-hover:opacity-100"
                        onClick={() => props.onOpen(l.id)} title="Edit">✎</button>
                <button className="px-1 text-xs text-slate-400 opacity-0 transition hover:text-emerald-300 group-hover:opacity-100"
                        onClick={() => props.onDuplicate(l.id)} title="Duplicate">⧉</button>
                <button className="px-1 text-xs text-slate-400 opacity-0 transition hover:text-red-400 group-hover:opacity-100"
                        onClick={() => props.onDelete(l.id)} title="Delete">✕</button>
              </div>
            </li>
          )
        })}
        {visible.length === 0 && (
          <li className="rounded-lg border border-dashed border-slate-700 p-4 text-center text-sm text-slate-500">
            {labels.length ? 'No labels match that search.' : 'No labels yet — add one to get started.'}
          </li>
        )}
      </ul>
    </div>
  )
}
