import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { ThreeMFLoader } from 'three/examples/jsm/loaders/3MFLoader.js'
import type { PlateEstimate, PlatePlacement } from '../types'

/**
 * See the build plate before downloading it.
 *
 * The parts are the real rendered geometry at the exact positions the export will use —
 * the layout comes from the same server endpoint the plate build uses, so the preview
 * can't drift from the file. Each DISTINCT label is fetched once and cloned per copy,
 * which is also how the exported 3MF shares geometry.
 *
 * Rendering is genuinely per-item work (a label that has never been rendered takes about
 * half a second), so progress is reported item by item rather than leaving a blank panel.
 */
export function PlatePreview({ estimate, onClose }: {
  estimate: PlateEstimate
  onClose: () => void
}) {
  const mountRef = useRef<HTMLDivElement>(null)
  const [done, setDone] = useState(0)
  const [total, setTotal] = useState(0)
  const [current, setCurrent] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    const mount = mountRef.current!
    const scene = new THREE.Scene()
    scene.background = new THREE.Color('#0f172a')
    const camera = new THREE.PerspectiveCamera(38, 1, 1, 5000)
    camera.up.set(0, 0, 1)

    let renderer: THREE.WebGLRenderer
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true })
    } catch (err) {
      setError('3D preview unavailable: no WebGL context. ' + (err as Error).message)
      return
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.domElement.style.cssText = 'display:block;width:100%;height:100%'
    mount.appendChild(renderer.domElement)

    scene.add(new THREE.AmbientLight(0xffffff, 1.15))
    const key = new THREE.DirectionalLight(0xffffff, 1.9)
    key.position.set(120, -180, 260)
    scene.add(key)

    const { plate_x: px, plate_y: py } = estimate

    // The build plate itself, so the packing is readable in context.
    const plate = new THREE.Mesh(
      new THREE.PlaneGeometry(px, py),
      new THREE.MeshStandardMaterial({ color: '#1e293b', roughness: 0.95 }),
    )
    plate.position.set(px / 2, py / 2, -0.6)
    scene.add(plate)
    const grid = new THREE.GridHelper(Math.max(px, py), Math.round(Math.max(px, py) / 42))
    grid.rotation.x = Math.PI / 2
    grid.position.set(px / 2, py / 2, -0.5)
    ;(grid.material as THREE.Material).opacity = 0.25
    ;(grid.material as THREE.Material).transparent = true
    scene.add(grid)

    // Frame the OCCUPIED area, not the whole plate: a handful of 11mm-tall labels on a
    // 250mm plate would otherwise be a thin strip at the bottom of a mostly empty view.
    const used = estimate.placements.reduce(
      (a, p) => ({
        x0: Math.min(a.x0, p.x), y0: Math.min(a.y0, p.y),
        x1: Math.max(a.x1, p.x + p.w), y1: Math.max(a.y1, p.y + p.h),
      }),
      { x0: px, y0: py, x1: 0, y1: 0 },
    )
    const cx = (used.x0 + used.x1) / 2
    const cy = (used.y0 + used.y1) / 2
    const span = Math.max(used.x1 - used.x0, used.y1 - used.y0, 40)

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.08
    controls.target.set(cx, cy, 0)
    camera.position.set(cx, cy - span * 0.75, span * 0.95)
    controls.update()

    const resize = () => {
      const { clientWidth: w, clientHeight: h } = mount
      if (!w || !h) return
      renderer.setSize(w, h, false)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
    }
    const ro = new ResizeObserver(resize)
    ro.observe(mount)
    resize()

    let raf = 0
    const tick = () => {
      raf = requestAnimationFrame(tick)
      controls.update()
      renderer.render(scene, camera)
    }
    tick()

    // --- fetch each distinct label once, place every copy ----------------------
    let cancelled = false
    const distinct: PlatePlacement[] =
      [...new Map(estimate.placements.map((p) => [p.label_id, p])).values()]
    setTotal(distinct.length)

    ;(async () => {
      const cache = new Map<string, THREE.Group>()
      for (const [i, p] of distinct.entries()) {
        if (cancelled) return
        setCurrent(p.title)
        try {
          const res = await fetch(`/api/labels/${p.label_id}/download?fmt=3mf`)
          if (!res.ok) throw new Error(`HTTP ${res.status}`)
          const group = new ThreeMFLoader().parse(await res.arrayBuffer())
          group.traverse((child) => {
            const mesh = child as THREE.Mesh
            if (!mesh.isMesh) return
            const existing = mesh.material as THREE.Material & { color?: THREE.Color }
            mesh.material = new THREE.MeshStandardMaterial({
              color: existing?.color ?? new THREE.Color('#c0c0c0'),
              vertexColors: !!(mesh.geometry.attributes as Record<string, unknown>).color,
              roughness: 0.55, metalness: 0.1,
            })
          })
          cache.set(p.label_id, group)
        } catch (err) {
          if (!cancelled) setError(`Could not render "${p.title}": ${(err as Error).message}`)
        }
        setDone(i + 1)

        // Place every copy of this label as soon as it's available, so the plate fills in
        // as it goes instead of appearing all at once at the end.
        for (const place of estimate.placements.filter((q) => q.label_id === p.label_id)) {
          const src = cache.get(p.label_id)
          if (!src || cancelled) continue
          const clone = src.clone(true)
          clone.position.set(place.x, place.y, 0)
          scene.add(clone)
        }
      }
      if (!cancelled) setCurrent('')
    })()

    return () => {
      cancelled = true
      cancelAnimationFrame(raf)
      ro.disconnect()
      controls.dispose()
      renderer.dispose()
      mount.removeChild(renderer.domElement)
    }
  }, [estimate])

  const pct = total ? Math.round((done / total) * 100) : 0
  const working = total > 0 && done < total

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4"
         role="dialog" aria-modal="true" aria-label="Plate preview"
         onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="flex h-full max-h-[46rem] w-full max-w-5xl flex-col rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-5 py-3">
          <div>
            <h2 className="text-base font-semibold text-slate-100">Build plate preview</h2>
            <p className="text-xs text-slate-500">
              {estimate.parts} parts · {estimate.rows} rows · {estimate.used_y.toFixed(0)}mm deep
              · plate {estimate.plate_x}×{estimate.plate_y}mm
            </p>
          </div>
          <button className="text-slate-400 hover:text-slate-100" onClick={onClose} aria-label="Close">✕</button>
        </header>

        <div className="min-h-0 flex-1 p-4">
          <div ref={mountRef} className="h-full min-h-[16rem] w-full cursor-grab overflow-hidden rounded-xl border border-slate-700 active:cursor-grabbing" />
        </div>

        <footer className="space-y-2 border-t border-slate-800 px-5 py-3">
          <div className="flex items-center justify-between gap-3 text-xs">
            <span className={working ? 'text-emerald-300' : 'text-slate-500'}>
              {working
                ? `Rendering ${done + 1} of ${total}${current ? ` — ${current}` : ''}…`
                : total
                  ? `All ${total} label${total === 1 ? '' : 's'} rendered · drag to orbit, scroll to zoom`
                  : 'Nothing selected'}
            </span>
            <span className="text-slate-500">{pct}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
            <div className="h-full rounded-full bg-emerald-500 transition-all duration-300"
                 style={{ width: `${pct}%` }} />
          </div>
          {error && <p className="text-xs text-red-400">{error}</p>}
        </footer>
      </div>
    </div>
  )
}
