import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { ThreeMFLoader } from 'three/examples/jsm/loaders/3MFLoader.js'
import { api } from '../api'
import type { Label } from '../types'
import { labelWidthMm } from '../types'

/**
 * Live 3D preview. The server renders the real geometry (OpenSCAD → 3MF) and we
 * display that exact file — so what you see here is what a slicer will open,
 * colors included, rather than a re-implementation of the label in the browser.
 */
export function Preview({ label }: { label: Label }) {
  const mountRef = useRef<HTMLDivElement>(null)
  const modelRef = useRef<THREE.Group | null>(null)
  const sceneRef = useRef<THREE.Scene | null>(null)
  const frameRef = useRef<((radius: number, reset: boolean) => void) | null>(null)
  const framedOnce = useRef(false)
  const [status, setStatus] = useState<'idle' | 'rendering' | 'error'>('idle')
  const [error, setError] = useState('')

  // --- one-time scene setup -------------------------------------------------
  useEffect(() => {
    const mount = mountRef.current!
    const scene = new THREE.Scene()
    scene.background = new THREE.Color('#0f172a')
    sceneRef.current = scene

    const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 2000)

    // A machine without working WebGL (remote desktop, blacklisted GPU, hardware
    // acceleration off) throws here. Uncaught in an effect that unmounts the whole app,
    // so catch it and say so — a blank panel with no explanation is the worst outcome.
    let renderer: THREE.WebGLRenderer
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true })
    } catch (err) {
      setStatus('error')
      setError('3D preview unavailable: this browser could not create a WebGL context. '
               + 'Exports still work. ' + (err as Error).message)
      return
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))

    // CSS owns the canvas's LAYOUT size; setSize() below only sizes the drawing buffer.
    // Without this the canvas's intrinsic (attribute) size becomes its layout size, which
    // becomes the grid column's min-content width — a wide canvas then pushes the editor
    // column off the right edge of the page.
    renderer.domElement.style.display = 'block'
    renderer.domElement.style.width = '100%'
    renderer.domElement.style.height = '100%'
    mount.appendChild(renderer.domElement)

    scene.add(new THREE.AmbientLight(0xffffff, 1.1))
    const key = new THREE.DirectionalLight(0xffffff, 2.0)
    key.position.set(40, -60, 90)
    scene.add(key)
    const fill = new THREE.DirectionalLight(0xffffff, 0.7)
    fill.position.set(-60, 40, 40)
    scene.add(fill)

    // Orbit the way a slicer does. The hand-rolled version drove the camera from a single
    // azimuth with a fixed height, so a horizontal drag read as the model tumbling towards
    // you instead of spinning on a turntable, and there was no way to change elevation at
    // all. OrbitControls is the convention Bambu Studio / Fusion / Blender share.
    camera.up.set(0, 0, 1)                       // Z-up, like the slicer and the .scad
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.08
    controls.rotateSpeed = 0.9
    controls.zoomSpeed = 0.8
    controls.target.set(0, 0, 0)
    controls.minDistance = 15
    controls.maxDistance = 600

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

    // Frame the model, keeping whatever direction the user has orbited to. Distance is
    // fitted against the tighter field of view so a 3U label stays inside a narrow panel.
    const frame = (radius: number, reset: boolean) => {
      const vFov = (camera.fov * Math.PI) / 180
      const hFov = 2 * Math.atan(Math.tan(vFov / 2) * camera.aspect)
      const distance = (radius / Math.sin(Math.min(vFov, hFov) / 2)) * 1.1
      const dir = reset
        ? new THREE.Vector3(0.45, -0.78, 0.44).normalize()   // default 3/4 view
        : camera.position.clone().sub(controls.target).normalize()
      camera.position.copy(dir.multiplyScalar(distance)).add(controls.target)
      camera.updateProjectionMatrix()
      controls.update()
    }
    frameRef.current = frame
    frame(30, true)

    let raf = 0
    const tick = () => {
      raf = requestAnimationFrame(tick)
      controls.update()                 // damping needs a per-frame update
      renderer.render(scene, camera)
    }
    tick()

    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      controls.dispose()
      renderer.dispose()
      mount.removeChild(renderer.domElement)
    }
  }, [])

  // --- re-render on any parameter change (debounced) ------------------------
  useEffect(() => {
    const controller = new AbortController()
    const timer = setTimeout(async () => {
      setStatus('rendering')
      try {
        const buffer = await api.preview(label, controller.signal)
        const group = new ThreeMFLoader().parse(buffer)

        // OpenSCAD models are unlit-ish; give every mesh a material that shows depth.
        group.traverse((child) => {
          const mesh = child as THREE.Mesh
          if (!mesh.isMesh) return
          const existing = mesh.material as THREE.Material & { color?: THREE.Color; vertexColors?: boolean }
          mesh.material = new THREE.MeshStandardMaterial({
            color: existing?.color ?? new THREE.Color('#c0c0c0'),
            vertexColors: !!(mesh.geometry.attributes as Record<string, unknown>).color,
            roughness: 0.55,
            metalness: 0.1,
            flatShading: false,
          })
        })

        const box = new THREE.Box3().setFromObject(group)
        const center = box.getCenter(new THREE.Vector3())
        group.position.sub(center)                    // centre on the origin
        group.userData.radius = Math.max(box.getSize(new THREE.Vector3()).length() / 2, 10)

        const scene = sceneRef.current!
        if (modelRef.current) scene.remove(modelRef.current)
        scene.add(group)
        modelRef.current = group
        // Re-fit for the new size, but only snap back to the default view the first time —
        // after that, keep wherever the user has orbited to.
        frameRef.current?.(group.userData.radius as number, !framedOnce.current)
        framedOnce.current = true
        setStatus('idle')
        setError('')
      } catch (err) {
        if ((err as Error).name === 'AbortError') return
        setStatus('error')
        setError((err as Error).message)
      }
    }, 350)                                            // debounce typing
    return () => { clearTimeout(timer); controller.abort() }
  }, [JSON.stringify(label)])

  return (
    <div className="relative h-full w-full min-w-0 overflow-hidden rounded-xl border border-slate-700 bg-slate-900">
      <div ref={mountRef} className="h-full w-full cursor-grab active:cursor-grabbing" />
      <div className="pointer-events-none absolute left-3 top-3 rounded-md bg-slate-950/70 px-2 py-1 text-xs text-slate-300">
        {labelWidthMm(label).toFixed(0)} × 11 × 1.2 mm · {label.width_u}U
      </div>
      {status === 'rendering' && (
        <div className="pointer-events-none absolute right-3 top-3 rounded-md bg-emerald-500/20 px-2 py-1 text-xs text-emerald-300">
          rendering…
        </div>
      )}
      {status === 'error' && (
        <div className="absolute inset-x-3 bottom-3 rounded-md bg-red-950/90 px-3 py-2 text-xs text-red-200">
          {error || 'render failed'}
        </div>
      )}
      <div className="pointer-events-none absolute bottom-3 left-3 text-xs text-slate-500">drag to orbit · scroll to zoom</div>
    </div>
  )
}
