import { useEffect, useState } from 'react'
import { api } from '../api'
import type { FitReport, Label } from '../types'

/**
 * Warn when the text runs off the label — and offer the fix.
 *
 * The renderer never clips: text wider than the label simply continues past the edge, with
 * nothing in the export to suggest a problem. Without this you find out after slicing, or
 * after printing.
 */
export function FitWarning({ label, onApply }: {
  label: Label
  onApply: (patch: Partial<Label>) => void
}) {
  const [report, setReport] = useState<FitReport | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    // Same debounce as the preview — a fit check is a render, and the render is shared.
    const timer = setTimeout(() => {
      api.fitCheck(label, controller.signal).then(setReport).catch(() => {})
    }, 400)
    return () => { clearTimeout(timer); controller.abort() }
  }, [JSON.stringify(label)])

  if (!report || report.fits) return null

  const widen = () => report.suggested_width_u && onApply({ width_u: report.suggested_width_u })
  const shrink = () => {
    // Applied exactly as given: the server verified these sizes by rendering them.
    if (!report.suggested_text1_size || !report.suggested_text2_size) return
    onApply({
      text1: { ...label.text1, size: report.suggested_text1_size },
      text2: { ...label.text2, size: report.suggested_text2_size },
    })
  }

  return (
    <div className="rounded-lg border border-amber-700/60 bg-amber-500/10 p-3 text-xs text-amber-200"
         role="status">
      <div className="font-medium">This won't fit on the label.</div>
      <p className="mt-1 text-amber-200/80">{report.message}</p>
      <div className="mt-2 flex flex-wrap gap-2">
        {report.suggested_text1_size && (
          <button type="button" onClick={shrink}
                  className="rounded-md border border-amber-600/60 px-2 py-1 hover:bg-amber-500/15">
            Shrink text to {report.suggested_text1_size}mm
          </button>
        )}
        {report.suggested_width_u && (
          <button type="button" onClick={widen}
                  className="rounded-md border border-amber-600/60 px-2 py-1 hover:bg-amber-500/15">
            Use a {report.suggested_width_u}U label
          </button>
        )}
      </div>
    </div>
  )
}
