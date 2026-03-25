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

## Web App Usage

- **Backgrounds:** `#05172B` for main/sidebar; slightly lighter tints for cards/panels if needed.
- **Text on dark:** White or near-white (e.g. `#F5F5F5`); use `#FD4437` sparingly for emphasis.
- **Buttons:** Primary = `#FD4437` with white text; secondary = outline or transparent on `#05172B`.
- **Focus/active:** Accent red or a light border in `#FD4437`.
- **Font stack:** `'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`.

---

## Form Input Text Color Rule

Browser `<input>`, `<select>`, and `<textarea>` elements may render with a white/light browser-default background regardless of Tailwind background classes (especially `bg-surface-raised`). To ensure text is always readable:

- **Always use `text-navy-900` (`#05172B`) for input/select/textarea text** — not `text-ink-primary` (#F0F4F8).
- **Never use `bg-surface-input`** — this token is not defined in the Tailwind config and results in a white browser-default background.
- For textareas and inline `<textarea>` elements, use `bg-surface-raised text-navy-900`.
- `text-ink-primary` is correct for static display text on dark navy surfaces — but not for editable form fields.

---

## CSS Variables (reference)

```css
:root {
  --color-primary: #05172B;
  --color-accent: #FD4437;
  --font-primary: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}
```
