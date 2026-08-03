import { useRef } from 'react'
import { useDialog } from '../useDialog'

/**
 * What these labels are, and where they come from.
 *
 * A first-time visitor landed on a library of example labels with no explanation of the
 * system, the click-in socket, or the fact that you need bins with slots. And nothing
 * pointed at the project whose work all the geometry is — which matters, because for some
 * people this tool will be how they first meet Cullenect labels.
 */
export function AboutDialog({ onClose }: { onClose: () => void }) {
  const dialogRef = useRef<HTMLDivElement>(null)
  useDialog(dialogRef, onClose)

  const link = 'text-emerald-400 underline hover:text-emerald-300'

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-950/80 p-4"
         role="dialog" aria-modal="true" aria-label="About Cullenect labels"
         onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div ref={dialogRef} className="my-auto w-full max-w-2xl rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl">
        <header className="flex items-center justify-between border-b border-slate-800 px-5 py-3">
          <h2 className="text-base font-semibold text-slate-100">What are Cullenect labels?</h2>
          <button className="text-slate-400 hover:text-slate-100" onClick={onClose} aria-label="Close">✕</button>
        </header>

        <div className="space-y-4 px-5 py-4 text-sm leading-relaxed text-slate-300">
          <p>
            They're <strong className="text-slate-100">swappable labels for Gridfinity bins</strong>.
            A thin printed label <em>clicks</em> into a slot on the front of a bin and stays
            there — and pops out again when the drawer's contents change, so relabelling
            doesn't mean reprinting the bin.
          </p>

          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
              You need two things
            </h3>
            <ol className="list-inside list-decimal space-y-1 text-slate-400">
              <li><span className="text-slate-300">The labels</span> — that's what this tool makes.</li>
              <li>
                <span className="text-slate-300">Bins with a slot to take them.</span> Either
                print bins that already have Cullenect sockets, or cut a slot into your own
                design using the negative volume under <strong>Sockets</strong> above.
              </li>
            </ol>
          </div>

          <div>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
              What this tool adds
            </h3>
            <p className="text-slate-400">
              The upstream OpenSCAD customizer already generates a label perfectly well. This
              is for when you have <em>lots</em> of them: it keeps the list, lets you pick
              icons by looking at them rather than by name, and packs many labels onto one
              build plate in a single file.
            </p>
          </div>

          <div>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
              Printing them
            </h3>
            <p className="text-slate-400">
              The text and icons stand 0.2mm off the body, so a 0.1mm or 0.2mm layer height
              renders them cleanly. Export as <strong>3MF</strong> and the text arrives as its
              own colour group, so a slicer can assign a second filament — or just insert a
              colour change at the top layer on a single-extruder printer.
            </p>
          </div>

          <div className="rounded-lg border border-emerald-900/50 bg-emerald-500/5 p-3">
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-emerald-300">
              Credit where it's due
            </h3>
            <p className="text-slate-400">
              The label system, the socket standard and all the geometry are{' '}
              <a className={link} href="https://github.com/CullenJWebb/Cullenect-Labels"
                 target="_blank" rel="noreferrer">Cullenect Labels</a> by Cullen J Webb, used
              here unmodified. This tool just drives it. If you find it useful, the upstream
              project is the place to start — it's also on{' '}
              <a className={link} href="https://makerworld.com/en/models/446624"
                 target="_blank" rel="noreferrer">MakerWorld</a> with pre-sliced profiles.
            </p>
          </div>

          <div>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
              Also worth knowing
            </h3>
            <ul className="list-inside list-disc space-y-1 text-slate-400">
              <li>
                <a className={link} href="https://github.com/ostat/gridfinity_extended_openscad"
                   target="_blank" rel="noreferrer">Gridfinity Extended</a> — generates bins
                with Cullenect slots already built in.
              </li>
              <li>
                <a className={link} href="https://github.com/ndevenish/gflabel"
                   target="_blank" rel="noreferrer">gflabel</a> — a Python label generator with
                a large icon set, if you'd rather work from a command line.
              </li>
            </ul>
          </div>
        </div>

        <footer className="flex justify-end border-t border-slate-800 px-5 py-3">
          <button className="rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-500"
                  onClick={onClose}>Got it</button>
        </footer>
      </div>
    </div>
  )
}
