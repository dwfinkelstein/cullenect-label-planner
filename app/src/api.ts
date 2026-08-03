import type { FitReport, Label, Meta, PlateEstimate, PlateSettings } from './types'

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error((await res.text().catch(() => '')) || `HTTP ${res.status}`)
  return res.json() as Promise<T>
}

export const api = {
  meta: () => fetch('/api/meta').then(json<Meta>),
  settings: () => fetch('/api/settings').then(json<PlateSettings>),
  saveSettings: (s: PlateSettings) =>
    fetch('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(s),
    }).then(json<PlateSettings>),
  health: () => fetch('/api/health').then(json<{ openscad: string; color_3mf: boolean }>),

  list: () => fetch('/api/labels').then(json<Label[]>),
  create: (label: Label) =>
    fetch('/api/labels', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(label),
    }).then(json<Label>),
  update: (id: string, label: Label) =>
    fetch(`/api/labels/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(label),
    }).then(json<Label>),
  remove: async (id: string) => {
    const res = await fetch(`/api/labels/${id}`, { method: 'DELETE' })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
  },
  reorder: (order: string[]) =>
    fetch('/api/labels/reorder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ order }),
    }).then(json<Label[]>),

  /** Render an unsaved label; returns the raw 3MF for the 3D preview. */
  preview: async (label: Label, signal?: AbortSignal): Promise<ArrayBuffer> => {
    const res = await fetch('/api/render/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(label),
      signal,
    })
    if (!res.ok) throw new Error((await res.text().catch(() => '')) || `HTTP ${res.status}`)
    return res.arrayBuffer()
  },

  fitCheck: (label: Label, signal?: AbortSignal) =>
    fetch('/api/labels/fit-check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(label),
      signal,
    }).then(json<FitReport>),

  plateEstimate: (body: object) =>
    fetch('/api/plate/estimate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then(json<PlateEstimate>),

  bulkCreate: (text: string, template: Label) =>
    fetch('/api/labels/bulk', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, template }),
    }).then(json<Label[]>),

  importLibrary: (labels: Label[]) =>
    fetch('/api/library/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ labels }),
    }).then(json<Label[]>),
}

/** Trigger a browser download from a POST response (plate) or a GET url. */
export async function download(url: string, init?: RequestInit) {
  const res = await fetch(url, init)
  if (!res.ok) throw new Error((await res.text().catch(() => '')) || `HTTP ${res.status}`)
  const blob = await res.blob()
  const disposition = res.headers.get('Content-Disposition') || ''
  const match = /filename="?([^"]+)"?/.exec(disposition)
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = match?.[1] || 'download.3mf'
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(a.href), 10_000)
}
