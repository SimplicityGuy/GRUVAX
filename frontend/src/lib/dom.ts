/**
 * Vanilla DOM helper for GRUVAX admin components.
 *
 * el() creates an element via document.createElement() and assigns properties
 * via typed property assignment — NEVER via innerHTML.
 *
 * This is a hard security constraint (T-05-05-01, boundary-editing.md):
 * label and catalog strings from the collection may contain characters that
 * would be interpreted as HTML if injected via innerHTML. el() sidesteps this
 * entirely by setting textContent and properties directly.
 *
 * Usage:
 *   const div = el('div', { className: 'foo', textContent: 'Hello' })
 *   const btn = el('button', { role: 'slider', 'aria-valuenow': 50 }, child1, child2)
 *   parent.replaceChildren(...nodes)
 */

type ElProps<K extends keyof HTMLElementTagNameMap> = {
  [P in string]?: unknown
} & Partial<{
  className: string
  id: string
  textContent: string
  role: string
  tabIndex: number
  title: string
  'aria-label': string
  'aria-valuemin': string | number
  'aria-valuemax': string | number
  'aria-valuenow': string | number
  'aria-modal': string
  'aria-labelledby': string
  'aria-hidden': string
  'aria-live': string
  'aria-expanded': string
  type: string
  disabled: boolean
  style: Partial<CSSStyleDeclaration>
  dataset: Record<string, string>
  onClick: (ev: MouseEvent) => void
  onPointerDown: (ev: PointerEvent) => void
  onPointerMove: (ev: PointerEvent) => void
  onPointerUp: (ev: PointerEvent) => void
  onKeyDown: (ev: KeyboardEvent) => void
}> & Partial<HTMLElementTagNameMap[K]>

/**
 * Create an HTML element with typed property assignment.
 * Never assigns innerHTML. Children are appended as Node|string children.
 */
export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  props?: ElProps<K> | null,
  ...children: (Node | string)[]
): HTMLElementTagNameMap[K] {
  const elem = document.createElement(tag)

  if (props) {
    const {
      className,
      id,
      textContent,
      role,
      tabIndex,
      title,
      type,
      disabled,
      style,
      dataset,
      onClick,
      onPointerDown,
      onPointerMove,
      onPointerUp,
      onKeyDown,
      ...rest
    } = props as Record<string, unknown>

    if (className !== undefined) elem.className = String(className)
    if (id !== undefined) elem.id = String(id)
    if (textContent !== undefined) elem.textContent = String(textContent)
    if (role !== undefined) elem.setAttribute('role', String(role))
    if (tabIndex !== undefined) elem.tabIndex = Number(tabIndex)
    if (title !== undefined) elem.title = String(title)
    if (type !== undefined && 'type' in elem) (elem as HTMLInputElement).type = String(type)
    if (disabled !== undefined && 'disabled' in elem) (elem as HTMLButtonElement).disabled = Boolean(disabled)

    if (style && typeof style === 'object') {
      Object.assign(elem.style, style)
    }

    if (dataset && typeof dataset === 'object') {
      for (const [k, v] of Object.entries(dataset)) {
        elem.dataset[k] = v
      }
    }

    // Event listeners
    if (typeof onClick === 'function') elem.addEventListener('click', onClick as EventListener)
    if (typeof onPointerDown === 'function') elem.addEventListener('pointerdown', onPointerDown as EventListener)
    if (typeof onPointerMove === 'function') elem.addEventListener('pointermove', onPointerMove as EventListener)
    if (typeof onPointerUp === 'function') elem.addEventListener('pointerup', onPointerUp as EventListener)
    if (typeof onKeyDown === 'function') elem.addEventListener('keydown', onKeyDown as EventListener)

    // ARIA attributes and other string attributes
    for (const [k, v] of Object.entries(rest)) {
      if (v === undefined || v === null) continue
      if (k.startsWith('aria-') || k.startsWith('data-')) {
        elem.setAttribute(k, String(v))
      }
    }
  }

  for (const child of children) {
    if (typeof child === 'string') {
      elem.appendChild(document.createTextNode(child))
    } else {
      elem.appendChild(child)
    }
  }

  return elem
}
