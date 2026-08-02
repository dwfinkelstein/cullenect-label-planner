// Shared field group for one text block. The full editor panel it used to belong to was
// retired in favour of editing in the label dialog — one editing surface, and nothing to
// push off-screen at a narrow or ultrawide viewport.
import type { Meta, TextBlock } from '../types'

const field = 'w-full rounded-md border border-slate-700 bg-slate-800 px-2 py-1.5 text-sm text-slate-100 focus:border-emerald-500 focus:outline-none'
const labelCls = 'block text-[11px] font-medium uppercase tracking-wide text-slate-400'

export function TextBlockFields({
  value, onChange, meta, prefix,
}: { value: TextBlock; onChange: (v: TextBlock) => void; meta: Meta | null; prefix: string }) {
  const set = <K extends keyof TextBlock>(k: K, v: TextBlock[K]) => onChange({ ...value, [k]: v })
  return (
    <div className="grid grid-cols-2 gap-2">
      <div className="col-span-2">
        <label className={labelCls} htmlFor={`${prefix}-text`}>Text</label>
        <input id={`${prefix}-text`} className={field} value={value.text}
               onChange={(e) => set('text', e.target.value)} placeholder="e.g. M3 x 12" />
      </div>
      <div>
        <label className={labelCls} htmlFor={`${prefix}-align`}>Align</label>
        <select id={`${prefix}-align`} className={field} value={value.align}
                onChange={(e) => set('align', e.target.value as TextBlock['align'])}>
          <option value="left">left</option><option value="center">center</option><option value="right">right</option>
        </select>
      </div>
      <div>
        <label className={labelCls} htmlFor={`${prefix}-size`}>Size (mm)</label>
        <input id={`${prefix}-size`} className={field} type="number" step="0.1" min="1" max="11" value={value.size}
               onChange={(e) => set('size', Number(e.target.value))} />
      </div>
      <div>
        <label className={labelCls} htmlFor={`${prefix}-font`}>Font</label>
        <select id={`${prefix}-font`} className={field} value={value.font} onChange={(e) => set('font', e.target.value)}>
          {(meta?.fonts ?? [value.font]).map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
      </div>
      <div>
        <label className={labelCls} htmlFor={`${prefix}-style`}>Style</label>
        <select id={`${prefix}-style`} className={field} value={value.style} onChange={(e) => set('style', e.target.value)}>
          {(meta?.font_styles ?? [value.style]).map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      <div>
        <label className={labelCls} htmlFor={`${prefix}-dx`}>Nudge X</label>
        <input id={`${prefix}-dx`} className={field} type="number" step="0.1" value={value.dx}
               onChange={(e) => set('dx', Number(e.target.value))} />
      </div>
      <div>
        <label className={labelCls} htmlFor={`${prefix}-dy`}>Nudge Y</label>
        <input id={`${prefix}-dy`} className={field} type="number" step="0.1" value={value.dy}
               onChange={(e) => set('dy', Number(e.target.value))} />
      </div>
    </div>
  )
}
