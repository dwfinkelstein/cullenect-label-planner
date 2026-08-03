import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { ThreeMFLoader } from 'three/examples/jsm/loaders/3MFLoader.js'

/**
 * Displays whatever 3MF a URL returns. Split out from the label preview because the
 * accessories aren't labels — they're the socket models — but they deserve the same
 * "look at the real thing before you print it" treatment.
 */
export function ModelViewer({ url, className = '' }: { url: string; className?: string }) {
  const mountRef = useRef<HTMLDivElement>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [error, setError] = useState('')

  useEffect(() => {
    const mount = mountRef.current!
    const scene = new THREE.Scene()
    scene.background = new THREE.Color('#0f172a')
    const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 3000)
    camera.up.set(0, 0, 1)

    let renderer: THREE.WebGLRenderer
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true })
    } catch (err) {
      setStatus('error')
      setError('3D preview unavailable: no WebGL context. Downloads still work.')
      return
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.domElement.style.cssText = 'display:block;width:100%;height:100%'
    mount.appendChild(renderer.domElement)

    scene.add(new THREE.AmbientLight(0xffffff, 1.15))
    const key = new THREE.DirectionalLight(0xffffff, 1.9)
    key.position.set(40, -60, 90)
    scene.add(key)

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.08

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
    const tick = () => { raf = requestAnimationFrame(tick); controls.update(); renderer.render(scene, camera) }
    tick()

    let cancelled = false
    ;(async () => {
      setStatus('loading')
      try {
        const res = await fetch(url)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const group = new ThreeMFLoader().parse(await res.arrayBuffer())
        if (cancelled) return
        group.traverse((child) => {
          const mesh = child as THREE.Mesh
          if (!mesh.isMesh) return
          mesh.material = new THREE.MeshStandardMaterial({
            color: new THREE.Color('#c7c9cc'), roughness: 0.6, metalness: 0.1,
          })
        })
        const box = new THREE.Box3().setFromObject(group)
        const centre = box.getCenter(new THREE.Vector3())
        group.position.sub(centre)
        scene.add(group)

        const radius = Math.max(box.getSize(new THREE.Vector3()).length() / 2, 8)
        const vFov = (camera.fov * Math.PI) / 180
        const hFov = 2 * Math.atan(Math.tan(vFov / 2) * camera.aspect)
        const distance = (radius / Math.sin(Math.min(vFov, hFov) / 2)) * 1.15
        camera.position.copy(new THREE.Vector3(0.4, -0.8, 0.45).normalize()
          .multiplyScalar(distance))
        controls.target.set(0, 0, 0)
        controls.update()
        setStatus('ready')
      } catch (err) {
        if (!cancelled) { setStatus('error'); setError((err as Error).message) }
      }
    })()

    return () => {
      cancelled = true
      cancelAnimationFrame(raf)
      ro.disconnect()
      controls.dispose()
      renderer.dispose()
      mount.removeChild(renderer.domElement)
    }
  }, [url])

  return (
    <div className={`relative min-w-0 overflow-hidden rounded-xl border border-slate-700 bg-slate-900 ${className}`}>
      <div ref={mountRef} className="h-full w-full cursor-grab active:cursor-grabbing" />
      {status === 'loading' && (
        <div className="pointer-events-none absolute right-3 top-3 rounded-md bg-emerald-500/20 px-2 py-1 text-xs text-emerald-300">
          rendering…
        </div>
      )}
      {status === 'error' && (
        <div className="absolute inset-x-3 bottom-3 rounded-md bg-red-950/90 px-3 py-2 text-xs text-red-200">
          {error}
        </div>
      )}
      {status === 'ready' && (
        <div className="pointer-events-none absolute bottom-3 left-3 text-xs text-slate-500">
          drag to orbit · scroll to zoom
        </div>
      )}
    </div>
  )
}
