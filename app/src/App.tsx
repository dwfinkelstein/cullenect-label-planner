import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, download } from './api'
import { AccessoriesDialog } from './components/AccessoriesDialog'
import { BulkPasteDialog } from './components/BulkPasteDialog'
import { LabelDialog } from './components/LabelDialog'
import { LabelList } from './components/LabelList'
import { PlatePreview } from './components/PlatePreview'
import { Preview } from './components/Preview'
import type { Label, Meta, PlateEstimate, PlateSettings } from './types'
import { emptyLabel, labelTitle } from './types'

const btn = 'rounded-md border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 hover:border-slate-500 hover:text-white disabled:opacity-40'
const btnPrimary = 'rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-40'

export default function App() {
  const [labels, setLabels] = useState<Label[]>([])
  const [meta, setMeta] = useState<Meta | null>(null)
  const [health, setHealth] = useState<{ openscad: string; color_3mf: boolean } | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [editing, setEditing] = useState<Label | null>(null)
  const [platePreview, setPlatePreview] = useState(false)
  const [checked, setChecked] = useState<Set<string>>(new Set())
  const [plate, setPlate] = useState<PlateSettings>({ plate_x: 250, plate_y: 250, gap: 3 })
  const [estimate, setEstimate] = useState<PlateEstimate | null>(null)
  const [busy, setBusy] = useState('')
  const [toast, setToast] = useState('')
  const [newOpen, setNewOpen] = useState(false)
  const [bulkOpen, setBulkOpen] = useState(false)
  const [accessoriesOpen, setAccessoriesOpen] = useState(false)
  const [activeTags, setActiveTags] = useState<string[]>([])
  const fileRef = useRef<HTMLInputElement>(null)
  const settingsLoaded = useRef(false)

  const knownTags = useMemo(() => [...new Set(labels.flatMap((l) => l.tags))].sort(),
                             [labels])
  const selected = useMemo(() => labels.find((l) => l.id === selectedId) ?? null,
                           [labels, selectedId])

  const flash = (msg: string) => { setToast(msg); setTimeout(() => setToast(''), 3500) }

  const refresh = useCallback(async (selectFirst = false) => {
    const list = await api.list()
    setLabels(list)
    setChecked(new Set(list.map((l) => l.id)))
    if (selectFirst && list.length) setSelectedId(list[0].id)
    return list
  }, [])

  useEffect(() => {
    refresh(true).catch((e) => flash(`Could not load the library: ${e.message}`))
    api.meta().then(setMeta).catch(() => {})
    api.health().then(setHealth).catch(() => {})
    // Plate size is a property of your printer, so it shouldn't be re-entered every visit.
    api.settings().then((s) => { setPlate(s); settingsLoaded.current = true })
      .catch(() => { settingsLoaded.current = true })
  }, [refresh])

  // Persist plate settings after they settle, so typing a bed size isn't 3 writes per digit.
  useEffect(() => {
    if (!settingsLoaded.current) return      // don't save the defaults over the stored ones
    const timer = setTimeout(() => { api.saveSettings(plate).catch(() => {}) }, 800)
    return () => clearTimeout(timer)
  }, [plate])

  // Plate estimate follows the checked set + plate settings.
  useEffect(() => {
    const ids = [...checked]
    if (!ids.length) { setEstimate(null); return }
    const timer = setTimeout(() => {
      api.plateEstimate({ label_ids: ids, ...plate }).then(setEstimate).catch(() => setEstimate(null))
    }, 200)
    return () => clearTimeout(timer)
  }, [checked, plate, labels])

  const select = (id: string) => setSelectedId(id)
  const edit = (id: string) => {
    const found = labels.find((l) => l.id === id)
    if (found) { setSelectedId(id); setEditing(found) }
  }

  const saveEdited = async (updatedDraft: Label) => {
    const id = updatedDraft.id
    const updated = await api.update(id, updatedDraft)
    setLabels((prev) => prev.map((l) => (l.id === id ? updated : l)))
    setEditing(null)
    flash('Saved to the library.')
  }

  const addLabel = async (base?: Label) => {
    const seed = base ? { ...structuredClone(base), id: '', name: `${labelTitle(base)} copy` } : emptyLabel()
    const created = await api.create(seed as Label)
    setLabels((prev) => [...prev, created])
    setChecked((prev) => new Set(prev).add(created.id))
    setSelectedId(created.id)
  }

  const removeLabel = async (id: string) => {
    const target = labels.find((l) => l.id === id)
    if (!target || !confirm(`Delete "${labelTitle(target)}" from the library?`)) return
    await api.remove(id)
    const rest = labels.filter((l) => l.id !== id)
    setLabels(rest)
    setChecked((prev) => { const next = new Set(prev); next.delete(id); return next })
    if (selectedId === id) setSelectedId(rest[0]?.id ?? null)
    setEditing(null)
  }

  const setQty = async (id: string, qty: number) => {
    const target = labels.find((l) => l.id === id)
    if (!target) return
    const updated = await api.update(id, { ...target, qty })
    setLabels((prev) => prev.map((l) => (l.id === id ? updated : l)))
  }

  const move = async (id: string, dir: -1 | 1) => {
    const i = labels.findIndex((l) => l.id === id)
    const j = i + dir
    if (i < 0 || j < 0 || j >= labels.length) return
    const next = [...labels]
    ;[next[i], next[j]] = [next[j], next[i]]
    setLabels(next)
    await api.reorder(next.map((l) => l.id))
  }

  const toggle = (id: string) =>
    setChecked((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n })

  const downloadPlate = async () => {
    setBusy('plate')
    try {
      await download('/api/plate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label_ids: [...checked], ...plate }),
      })
    } catch (e) { flash(`Plate export failed: ${(e as Error).message}`) } finally { setBusy('') }
  }

  const downloadOne = async (fmt: '3mf' | 'stl') => {
    if (!selectedId) return
    setBusy(fmt)
    try { await download(`/api/labels/${selectedId}/download?fmt=${fmt}`) }
    catch (e) { flash(`Export failed: ${(e as Error).message}`) } finally { setBusy('') }
  }

  const importLibrary = async (file: File) => {
    try {
      const parsed = JSON.parse(await file.text())
      const incoming: Label[] = Array.isArray(parsed) ? parsed : parsed.labels
      if (!Array.isArray(incoming)) throw new Error('expected a labels array')
      if (!confirm(`Replace the library with ${incoming.length} imported labels?`)) return
      await api.importLibrary(incoming)
      await refresh(true)
      flash(`Imported ${incoming.length} labels.`)
    } catch (e) { flash(`Import failed: ${(e as Error).message}`) }
  }

  return (
    // Fixed-height app shell ONLY at lg, where the three columns fit side by side. Below
    // that the columns stack and the page must be free to grow and scroll — pinning it to
    // h-screen there left the editor laid out past the bottom edge with nothing scrollable,
    // i.e. genuinely unreachable (CULL-RULE-10).
    <div className="flex min-h-screen flex-col bg-slate-950 text-slate-100 lg:h-screen">
      <header className="flex shrink-0 flex-wrap items-center gap-3 border-b border-slate-800 px-4 py-2.5">
        <h1 className="text-base font-semibold">
          Cullenect <span className="text-emerald-400">Label Planner</span>
        </h1>
        <span className="hidden text-xs text-slate-500 sm:inline">
          Gridfinity labels · library of {labels.length} · exports colored 3MF
        </span>
        <div className="ml-auto flex items-center gap-2">
          <button className={btnPrimary} onClick={() => setNewOpen(true)}>+ New label</button>
          <button className={btn} onClick={() => setBulkOpen(true)}>Paste a list</button>
          <button className={btn} onClick={() => setAccessoriesOpen(true)}>Sockets</button>
          <button className={btn} onClick={() => download('/api/library/export')}>Export JSON</button>
          <button className={btn} onClick={() => fileRef.current?.click()}>Import JSON</button>
          <input ref={fileRef} type="file" accept="application/json" className="hidden"
                 onChange={(e) => { const f = e.target.files?.[0]; if (f) importLibrary(f); e.target.value = '' }} />
        </div>
      </header>

      {/* Two columns since editing moved into a dialog. Capped and centred: on an ultrawide
          (3440px) a 1fr column otherwise absorbs every extra pixel and leaves a huge void. */}
      <main className="mx-auto grid w-full max-w-[1600px] flex-1 grid-cols-1 gap-3 p-3 lg:min-h-0 lg:grid-cols-[24rem_1fr]">
        {/* Stacked, the list is capped so it can't push the preview off-screen; as a grid
            column it just fills the row. */}
        <div className="h-[42vh] rounded-xl border border-slate-800 bg-slate-900/40 p-3 lg:h-auto lg:min-h-0">
          <LabelList
            labels={labels}
            selectedId={selectedId}
            dirtyId={null}
            checked={checked}
            onSelect={select}
            onOpen={edit}
            onToggle={toggle}
            onToggleAll={(on) => setChecked(on ? new Set(labels.map((l) => l.id)) : new Set())}
            onQty={setQty}
            onDuplicate={(id) => { const l = labels.find((x) => x.id === id); if (l) addLabel(l) }}
            onDelete={removeLabel}
            onMove={move}
            activeTags={activeTags}
            onTagsChange={setActiveTags}
          />
        </div>

        {/* min-w-0: a 1fr grid track defaults to min-width:auto, so it cannot shrink below
            its content's min-content width. Anything wide in here (a canvas reporting an
            intrinsic size, the plate controls) would otherwise widen the track and push the
            editor column off the right edge of the page. */}
        <div className="flex min-h-0 min-w-0 flex-col gap-3">
          {/* A real minimum height so the preview stays legible when the layout stacks —
              as a flex child of an auto-height column it otherwise collapsed to ~60px. */}
          <div className="min-h-[20rem] flex-1 lg:min-h-0">
            {selected ? <Preview label={selected} /> : (
              <div className="flex h-full items-center justify-center rounded-xl border border-dashed border-slate-700 text-slate-500">
                Select or add a label to preview it.
              </div>
            )}
          </div>

          <div className="min-w-0 shrink-0 rounded-xl border border-slate-800 bg-slate-900/60 p-3">
            <div className="flex flex-wrap items-end gap-3">
              <div>
                <div className="text-[11px] uppercase tracking-wide text-slate-400">Build plate</div>
                <div className="mt-1 flex items-center gap-1 text-sm">
                  <input className="w-16 rounded border border-slate-700 bg-slate-800 px-1.5 py-1 text-center" type="number"
                         value={plate.plate_x} onChange={(e) => setPlate({ ...plate, plate_x: Number(e.target.value) })} />
                  <span className="text-slate-500">×</span>
                  <input className="w-16 rounded border border-slate-700 bg-slate-800 px-1.5 py-1 text-center" type="number"
                         value={plate.plate_y} onChange={(e) => setPlate({ ...plate, plate_y: Number(e.target.value) })} />
                  <span className="text-slate-500">mm · gap</span>
                  <input className="w-14 rounded border border-slate-700 bg-slate-800 px-1.5 py-1 text-center" type="number" step="0.5"
                         value={plate.gap} onChange={(e) => setPlate({ ...plate, gap: Number(e.target.value) })} />
                </div>
              </div>
              <div className="text-sm text-slate-400">
                {estimate ? (
                  estimate.fits
                    ? <>{estimate.parts} parts · {estimate.rows} rows · {estimate.used_y.toFixed(0)}mm deep</>
                    : <span className="text-amber-400">{estimate.message}</span>
                ) : <span className="text-slate-600">nothing selected</span>}
              </div>
              <div className="ml-auto flex gap-2">
                <button className={btn} disabled={!selectedId || busy === 'stl'} onClick={() => downloadOne('stl')}>
                  This label · STL
                </button>
                <button className={btn} disabled={!selectedId || busy === '3mf'} onClick={() => downloadOne('3mf')}>
                  This label · 3MF
                </button>
                <button className={btn} disabled={!estimate?.fits} onClick={() => setPlatePreview(true)}>
                  Preview plate
                </button>
                <button className={btnPrimary} disabled={!estimate?.fits || busy === 'plate'} onClick={downloadPlate}>
                  {busy === 'plate' ? 'Rendering…' : 'Download plate 3MF'}
                </button>
              </div>
            </div>
          </div>
        </div>

      </main>

      <footer className="flex shrink-0 items-center gap-3 border-t border-slate-800 px-4 py-1.5 text-[11px] text-slate-500">
        <span>
          Geometry: <a className="text-slate-400 underline" href="https://github.com/CullenJWebb/Cullenect-Labels">Cullenect Labels</a> (MIT, Cullen J Webb)
        </span>
        {!!meta?.fonts_missing?.length && (
          <span className="text-amber-400" title="OpenSCAD will silently substitute another face">
            Font not installed: {meta.fonts_missing.join(', ')}
          </span>
        )}
        {health && (
          <span className="ml-auto">
            {health.openscad} · colored 3MF {health.color_3mf ? 'available' : 'UNAVAILABLE'}
          </span>
        )}
      </footer>

      {newOpen && (
        <LabelDialog
          mode="create"
          meta={meta}
          knownTags={knownTags}
          onCancel={() => setNewOpen(false)}
          onSubmit={async (l) => {
            const created = await api.create(l)
            setLabels((prev) => [...prev, created])
            setChecked((prev) => new Set(prev).add(created.id))
            setSelectedId(created.id)
            setNewOpen(false)
            flash(`Added "${labelTitle(created)}".`)
          }}
        />
      )}

      {bulkOpen && (
        <BulkPasteDialog
          meta={meta}
          knownTags={knownTags}
          onCancel={() => setBulkOpen(false)}
          onDone={(created) => {
            setLabels((prev) => [...prev, ...created])
            setChecked((prev) => {
              const next = new Set(prev)
              created.forEach((l) => next.add(l.id))
              return next
            })
            if (created.length) setSelectedId(created[0].id)
            setBulkOpen(false)
            flash(`Added ${created.length} label${created.length === 1 ? '' : 's'}.`)
          }}
        />
      )}

      {editing && (
        <LabelDialog
          mode="edit"
          initial={editing}
          meta={meta}
          knownTags={knownTags}
          onCancel={() => setEditing(null)}
          onSubmit={saveEdited}
          onDelete={async (l) => { await removeLabel(l.id) }}
        />
      )}

      {platePreview && estimate?.fits && (
        <PlatePreview estimate={estimate} onClose={() => setPlatePreview(false)} />
      )}

      {accessoriesOpen && <AccessoriesDialog onClose={() => setAccessoriesOpen(false)} />}

      {toast && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 rounded-lg bg-slate-800 px-4 py-2 text-sm text-slate-100 shadow-lg ring-1 ring-slate-700">
          {toast}
        </div>
      )}
    </div>
  )
}
