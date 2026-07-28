# Design System — Branding & Web App

## Typography
- **Primary font:** Inter (sans-serif)
- Use Inter for UI, headings, and body copy. Load via Google Fonts or `@font-face`.

---

## Color Palette

### Primary (Dark Navy)
| Format | Value |
|--------|--------|
| Hex | `#05172B` |
| RGB | 5, 23, 43 |
| CMYK | 100, 85, 50, 68 |
| Pantone | 5395 C |

**Use for:** Primary backgrounds, headers, dark surfaces, primary buttons (with light text).

### Accent (Warm Red)
| Format | Value |
|--------|--------|
| Hex | `#FD4437` |
| RGB | 253, 68, 55 |
| CMYK | 0, 82, 74, 0 |
| Pantone | Warm Red C |

**Use for:** CTAs, links, highlights, alerts, icons, focus states.

---

## Text Hierarchy

Three ink tiers, each guaranteed to clear WCAG AA (4.5:1) against all three navy surfaces (`surface.base` `#05172B`, `surface.raised` `#0a2440`, `surface.overlay` `#0e3158`). Tokens live in `frontend/src/assets/brand.ts` (source of truth), mirrored in `frontend/src/styles/tokens.css` and `frontend/tailwind.config.ts`; a vitest regression test (`frontend/src/test/contrast.test.ts`) enforces the AA floor and the tier ordering.

| Token | Hex | On `base` | On `raised` | On `overlay` | Use for |
|---|---|---|---|---|---|
| `ink.primary` | `#F0F4F8` | 16.33:1 | 14.19:1 | 11.88:1 | Primary body/heading text |
| `ink.secondary` | `#C5D9EA` | 12.45:1 | 10.82:1 | 9.06:1 | Secondary text, chart axis/legend labels |
| `ink.muted` | `#A3C2DC` | 9.72:1 | 8.44:1 | 7.07:1 | Recessive labels — table `Th`, chart axis lines, unit/sub-labels |

**AA floor:** every tier must clear 4.5:1 on every surface. Don't add a tier or change these hexes without recomputing contrast against all three surfaces.

---

## Web App Usage

- **Backgrounds:** `#05172B` for main/sidebar; slightly lighter tints for cards/panels if needed.
- **Text on dark:** White or near-white (e.g. `#F5F5F5`); use `#FD4437` sparingly for emphasis.
- **Buttons:** Primary = `#FD4437` with white text; secondary = outline or transparent on `#05172B`.
- **Focus/active:** Accent red or a light border in `#FD4437`.
- **Font stack:** `'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`.

---

## Form Input Token Rule

All form fields (`<input>`, `<select>`, `<textarea>`) must use the dedicated `surface.input` token:

- **Background:** `bg-surface-input` (`#0a2440`) — defined in Tailwind config; renders as dark navy
- **Text:** `text-ink-primary` (`#F0F4F8`) — near-white, readable on the navy background
- **Never omit `bg-surface-input`** — without an explicit background class, browsers default to white and `text-ink-primary` becomes invisible
- The `Input` and `Select` UI components use `bg-surface-raised` (same value as `surface.input`); raw `<input>`/`<textarea>`/`<select>` elements must use `bg-surface-input` explicitly

---

## CSS Variables (reference)

```css
:root {
  --color-primary: #05172B;
  --color-accent: #FD4437;
  --font-primary: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}
```
