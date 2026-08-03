import { useEffect, useState } from 'react'
import { download } from '../api'
import { ModelViewer } from './ModelViewer'

const field = 'w-full rounded-md border border-slate-700 bg-slate-800 px-2 py-1.5 text-sm text-slate-100 focus:border-emerald-500 focus:outline-none'

/**
 * The socket models from the upstream project. Arguably the most useful part of the whole
 * system for anyone designing their own bins — and until now they were reachable only by
 * calling the API by hand.
 */
const ACCESSORIES: { kind: string; name: string; blurb: string }[] = [
  {
    kind: 'socket-test-fit',
    name: 'Socket test fit',
    blurb: 'A short socket to print and click a label into. Print this FIRST — it tells you ' +
           'whether your printer holds the tolerance before you commit to a batch of labels.',
  },
  {
    kind: 'socket-negative',
    name: 'Socket negative volume',
    blurb: 'The shape to SUBTRACT from your own model to cut a label slot into it. This is ' +
           'what lets you put Cullenect labels on bins you designed yourself.',
  },
  {
    kind: 'vertical-socket-test-fit',
    name: 'Vertical socket test fit',
    blurb: 'The same fit check for a label that slides in from the side rather than the front.',
  },
  {
    kind: 'vertical-socket-negative',
    name: 'Vertical socket negative volume',
    blurb: 'Subtract this for a side-loading slot.',
  },
  {
    kind: 'label-spacer',
    name: 'Label spacer',
    blurb: 'A shim for a socket that came out slightly loose — cheaper than reprinting the bin.',
  },
]

export function AccessoriesDialog({ onClose }: { onClose: () => void }) {
  const [kind, setKind] = useState(ACCESSORIES[0].kind)
  const [width, setWidth] = useState(1)
  const [busy, setBusy] = useState('')

  const current = ACCESSORIES.find((a) => a.kind === kind)!
  const url = `/api/accessories/${kind}?width_u=${width}&fmt=3mf`

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const get = async (fmt: '3mf' | 'stl') => {
    setBusy(fmt)
    try { await download(`/api/accessories/${kind}?width_u=${width}&fmt=${fmt}`) }
    finally { setBusy('') }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-950/80 p-4"
         role="dialog" aria-modal="true" aria-label="Sockets and test fits"
         onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="my-auto w-full max-w-3xl rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl">
        <header className="flex items-center justify-between border-b border-slate-800 px-5 py-3">
          <div>
            <h2 className="text-base font-semibold text-slate-100">Sockets &amp; test fits</h2>
            <p className="text-xs text-slate-500">
              The parts that go on the bin, rather than the label that clicks into it.
            </p>
          </div>
          <button className="text-slate-400 hover:text-slate-100" onClick={onClose} aria-label="Close">✕</button>
        </header>

        <div className="grid gap-5 p-5 md:grid-cols-[1fr_16rem]">
          <div className="space-y-3">
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wide text-slate-400"
                     htmlFor="acc-kind">Part</label>
              <select id="acc-kind" className={field} value={kind}
                      onChange={(e) => setKind(e.target.value)}>
                {ACCESSORIES.map((a) => <option key={a.kind} value={a.kind}>{a.name}</option>)}
              </select>
            </div>
            <p className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-xs leading-relaxed text-slate-400">
              {current.blurb}
            </p>
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wide text-slate-400"
                     htmlFor="acc-width">Width (Gridfinity U)</label>
              <input id="acc-width" className={field} type="number" step="0.1" min="0.1" max="8"
                     value={width} onChange={(e) => setWidth(Number(e.target.value))} />
              <p className="mt-1 text-[11px] text-slate-600">
                Match the label width you plan to use: {(width * 42 - 6).toFixed(0)}mm wide.
              </p>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-xs leading-relaxed text-slate-400">
              <strong className="text-slate-300">Getting the fit right.</strong> Print the test
              fit and try a label in it. It should go in with a click and stay put. Too tight or
              too loose is a tolerance difference in your printer, not a design error — the
              upstream project documents the offsets to adjust.
            </div>
          </div>

          <aside className="space-y-3">
            <ModelViewer url={url} className="h-56" />
            <div className="grid grid-cols-2 gap-2">
              <button className="rounded-md border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 hover:border-slate-500 disabled:opacity-40"
                      disabled={busy === 'stl'} onClick={() => get('stl')}>STL</button>
              <button className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-40"
                      disabled={busy === '3mf'} onClick={() => get('3mf')}>3MF</button>
            </div>
          </aside>
        </div>

        <footer className="border-t border-slate-800 px-5 py-3 text-xs text-slate-500">
          Socket geometry comes from the vendored{' '}
          <a className="text-slate-400 underline"
             href="https://github.com/CullenJWebb/Cullenect-Labels">Cullenect Labels</a>{' '}
          source — the same file the labels are built from, so the fit is the standard one.
        </footer>
      </div>
    </div>
  )
}
