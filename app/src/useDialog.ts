import { useEffect, useRef } from 'react'

const FOCUSABLE = [
  'a[href]', 'button:not([disabled])', 'input:not([disabled])', 'select:not([disabled])',
  'textarea:not([disabled])', '[tabindex]:not([tabindex="-1"])',
].join(',')

/**
 * Modal behaviour every dialog needs: Escape closes, focus moves in, focus stays in, and
 * focus goes back where it came from.
 *
 * Without the trap, tabbing walks straight out of the dialog into the page it's covering —
 * so a keyboard user ends up interacting with a UI that is visually behind an overlay. And
 * without the restore, closing drops focus at the top of the document instead of the
 * control that opened the dialog.
 */
export function useDialog(ref: React.RefObject<HTMLElement | null>, onClose: () => void) {
  const previouslyFocused = useRef<HTMLElement | null>(null)

  useEffect(() => {
    previouslyFocused.current = document.activeElement as HTMLElement | null

    // Let an autoFocus field win; otherwise focus the dialog's first control.
    const node = ref.current
    if (node && !node.contains(document.activeElement)) {
      const first = node.querySelector<HTMLElement>(FOCUSABLE)
      ;(first ?? node).focus()
    }

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { onClose(); return }
      if (e.key !== 'Tab' || !ref.current) return

      const items = [...ref.current.querySelectorAll<HTMLElement>(FOCUSABLE)]
        .filter((el) => el.offsetParent !== null)      // skip anything hidden
      if (!items.length) return
      const first = items[0]
      const last = items[items.length - 1]
      const active = document.activeElement as HTMLElement

      // Wrap at both ends, and pull focus back in if it has escaped the dialog.
      if (e.shiftKey && (active === first || !ref.current.contains(active))) {
        e.preventDefault(); last.focus()
      } else if (!e.shiftKey && (active === last || !ref.current.contains(active))) {
        e.preventDefault(); first.focus()
      }
    }

    window.addEventListener('keydown', onKey, true)
    return () => {
      window.removeEventListener('keydown', onKey, true)
      previouslyFocused.current?.focus?.()
    }
  }, [ref, onClose])
}
