import type { Fastener } from '../types'

/**
 * A row of clickable icons for one choice. The thumbnails are the REAL geometry — the
 * server projects the same OpenSCAD modules the label is built from to 2D SVG — so what
 * you click is what gets printed, and a dropdown of names is replaced by something you can
 * actually recognise at a glance.
 */

const pretty = (s: string) =>
  s === 'roundh' ? 'Round' : s.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())

function Tile({ label, src, selected, onClick }: {
  label: string; src?: string; selected: boolean; onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-pressed={selected}
      className={`flex w-[4.5rem] shrink-0 flex-col items-center gap-1 rounded-lg border p-1.5 transition ${
        selected
          ? 'border-emerald-500 bg-emerald-500/15'
          : 'border-slate-700 bg-slate-800/60 hover:border-slate-500'
      }`}
    >
      <span className="flex h-10 w-10 items-center justify-center">
        {src ? (
          // invert: the SVG is black-on-transparent from OpenSCAD; the UI is dark.
          <img src={src} alt={label} className="h-10 w-10 invert" loading="lazy" />
        ) : (
          <span className="text-lg text-slate-500">∅</span>
        )}
      </span>
      <span className="w-full truncate text-[10px] leading-tight text-slate-300">{label}</span>
    </button>
  )
}

export function IconRow({ title, options, value, onChange, srcFor, hint }: {
  title: string
  options: string[]
  value: string
  onChange: (v: string) => void
  srcFor: (option: string) => string | undefined
  hint?: string
}) {
  return (
    <div className="flex flex-col gap-1.5 sm:flex-row sm:items-start sm:gap-3">
      <div className="w-24 shrink-0 pt-2">
        <div className="text-[11px] font-medium uppercase tracking-wide text-slate-400">{title}</div>
        {hint && <div className="text-[10px] text-slate-600">{hint}</div>}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {options.map((o) => (
          <Tile
            key={o}
            label={o === 'none' ? 'None' : pretty(o)}
            src={o === 'none' ? undefined : srcFor(o)}
            selected={value === o}
            onClick={() => onChange(o)}
          />
        ))}
      </div>
    </div>
  )
}

/** The four fastener rows plus its two toggles, sharing one fastener value. */
export function FastenerPicker({ value, onChange, meta }: {
  value: Fastener
  onChange: (v: Fastener) => void
  meta: { fastener_heads: string[]; fastener_drivers: string[]; fastener_shafts: string[]; fastener_threads: string[] } | null
}) {
  const set = <K extends keyof Fastener>(k: K, v: Fastener[K]) => onChange({ ...value, [k]: v })
  const q = (o: Record<string, string | boolean>) =>
    Object.entries(o).map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join('&')

  return (
    <div className="space-y-3">
      <label className="flex items-center gap-2 text-sm text-slate-200">
        <input type="checkbox" checked={value.show} onChange={(e) => set('show', e.target.checked)} />
        Include a fastener icon
      </label>

      {value.show && (
        <>
          <IconRow
            title="Head" options={(meta?.fastener_heads ?? []).filter((h) => h !== 'none')}
            value={value.head} onChange={(v) => set('head', v)}
            srcFor={(o) => `/api/icons/head.svg?${q({ head: o, driver: value.driver, flange: value.flange })}`}
          />
          <IconRow
            title="Driver" options={(meta?.fastener_drivers ?? []).filter((d) => d !== 'none')}
            value={value.driver} onChange={(v) => set('driver', v)}
            srcFor={(o) => `/api/icons/driver.svg?${q({ driver: o })}`}
          />
          <IconRow
            title="Shaft" options={meta?.fastener_shafts ?? []}
            value={value.shaft} onChange={(v) => set('shaft', v)}
            srcFor={(o) => `/api/icons/fastener.svg?${q({ head: value.head, driver: value.driver, shaft: o, threads: value.threads, flange: value.flange, security: value.security })}`}
          />
          <IconRow
            title="Threads" options={meta?.fastener_threads ?? []}
            value={value.threads} onChange={(v) => set('threads', v)}
            srcFor={(o) => `/api/icons/fastener.svg?${q({ head: value.head, driver: value.driver, shaft: value.shaft, threads: o, flange: value.flange, security: value.security })}`}
          />
          <div className="flex flex-wrap gap-4 pl-0 text-sm text-slate-300 sm:pl-[6.75rem]">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={value.flange}
                     onChange={(e) => set('flange', e.target.checked)} /> Flanged head
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={value.security}
                     onChange={(e) => set('security', e.target.checked)} /> Security nub
            </label>
          </div>
        </>
      )}
    </div>
  )
}

export function HardwarePicker({ value, onChange, options }: {
  value: string; onChange: (v: string) => void; options: string[]
}) {
  return (
    <IconRow
      title="Hardware" options={options} value={value} onChange={onChange}
      srcFor={(o) => `/api/icons/hardware.svg?name=${encodeURIComponent(o)}`}
    />
  )
}
