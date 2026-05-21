# Deferred Items — 260521-fn0

## Pre-existing lint errors (out of scope — not caused by this quick task)

The following lint errors existed on the baseline commit `d5d9a52` before any changes were made in this task. The `eslint .` gate was already broken at baseline.

### Files NOT modified by this task:
- `AdminShell.tsx:39` — `react-hooks/purity`: `Date.now()` in `useState` initializer
- `AdminShell.tsx:68` — `react-hooks/set-state-in-effect`: `void pollSession()` in `useEffect`
- `AdminShell.tsx:80` — `react-hooks/set-state-in-effect`: `setIsLocked(false)` in `useEffect`
- `DiffPreviewSheet.tsx:65` — `react-hooks/set-state-in-effect`: `setIsValidating(true)` in `useEffect`

### Files modified by this task (but errors pre-existed):
- `CubeEditor.tsx:192` — `react-hooks/set-state-in-effect`: `setFields(...)` in `useEffect` (pre-existing pattern, not introduced by this task's string/class changes)
- `CubeEditor.tsx:292` — `react-hooks/set-state-in-effect`: `void runValidation(...)` in `useEffect` (pre-existing)
- `PinOverlay.tsx:48` — `react-hooks/immutability`: `submitPin` accessed before declaration (pre-existing hoisting pattern)
- `PinOverlay.tsx:77` — `@typescript-eslint/no-unused-vars`: `_` variable (pre-existing)

These are React Compiler lint rules (`react-hooks/purity`, `react-hooks/set-state-in-effect`, `react-hooks/immutability`) that require architectural changes to state initialization and effect patterns. Fixing them is outside the scope of this visual-conformance quick task.

**Recommended next action:** Create a separate quick task or Phase 3 plan to address React Compiler lint compliance for the admin shell.
