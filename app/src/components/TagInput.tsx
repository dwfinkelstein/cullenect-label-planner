import { useState } from 'react'

/**
 * Tag chips with add/remove and suggestions from tags already in the library.
 *
 * Tags are how a library stops being a flat list once it has a few hundred entries. They
 * were already stored and searched — there was just no way to put one on a label.
 */
export function TagInput({ value, suggestions, onChange }: {
  value: string[]
  suggestions: string[]
  onChange: (tags: string[]) => void
}) {
  const [draft, setDraft] = useState('')

  const add = (raw: string) => {
    // Normalised on the way in: tags are for grouping, and 'M3' vs 'm3' vs ' m3 ' being
    // three different groups is just an annoyance.
    const tag = raw.trim().toLowerCase().replace(/\s+/g, '-')
    if (tag && !value.includes(tag)) onChange([...value, tag])
    setDraft('')
  }

  const unused = suggestions.filter((s) => !value.includes(s)).slice(0, 8)

  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-1.5">
        {value.map((t) => (
          <span key={t} className="flex items-center gap-1 rounded-full border border-emerald-700/60 bg-emerald-500/10 px-2 py-0.5 text-xs text-emerald-200">
            {t}
            <button type="button" aria-label={`Remove tag ${t}`}
                    className="text-emerald-400/70 hover:text-emerald-200"
                    onClick={() => onChange(value.filter((x) => x !== t))}>✕</button>
          </span>
        ))}
        <input
          id="tag-input"
          className="min-w-[8rem] flex-1 rounded-md border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-slate-100 focus:border-emerald-500 focus:outline-none"
          placeholder={value.length ? 'add another…' : 'e.g. m3, electrical, drawer-3'}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); add(draft) }
            // Backspace on an empty box removes the last chip — the usual behaviour.
            if (e.key === 'Backspace' && !draft && value.length) onChange(value.slice(0, -1))
          }}
          onBlur={() => draft && add(draft)}
        />
      </div>
      {!!unused.length && (
        <div className="flex flex-wrap gap-1">
          {unused.map((s) => (
            <button key={s} type="button" onClick={() => add(s)}
                    className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-400 hover:border-slate-500 hover:text-slate-200">
              + {s}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
