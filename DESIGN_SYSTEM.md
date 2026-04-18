# MSTool-AI — Design System

> **Rule**: Every UI change MUST reference this document. No ad-hoc styling.
> **Last updated**: 2026-04-18

## Sources

Based on research from: OHIF Viewer theming, NHS App Design System, Nord Health
Design System, Material Design 3, Apple HIG, Radix Themes, and dark-mode best
practices from clinical software industry leaders.

---

## 1. Spacing (4px base grid)

All spacing uses multiples of 4px. No arbitrary values.

| Token | Value | Usage |
|-------|-------|-------|
| `space-1` | 4px | Tight inline gaps |
| `space-2` | 8px | Between related elements (icon + label) |
| `space-3` | 12px | Normal gap between elements |
| `space-4` | 16px | Card/container padding, section gaps |
| `space-5` | 24px | Between sections |
| `space-6` | 32px | Between major content blocks |
| `space-8` | 48px | Page-level vertical spacing |

---

## 2. Buttons

**EVERY button must use one of these three sizes.** No custom heights.

| Size | Height | Padding (H) | Font | Icon | Use case |
|------|--------|-------------|------|------|----------|
| **Small (sm)** | 28px | 8px 12px | 12px / 500 | 14px | Toolbars, secondary actions, badges |
| **Medium (md)** | 36px | 8px 16px | 13px / 500 | 16px | Default. Primary actions, forms |
| **Large (lg)** | 44px | 12px 20px | 14px / 600 | 18px | Main CTAs, touch targets |

### Icon-only buttons
- Same height as text buttons (28 / 36 / 44px)
- Square: `width = height` (28x28, 36x36, 44x44)
- Minimum touch target: 44x44px per Apple HIG / WCAG 2.5.8

### Border radius
- **Default**: `6px` (professional clinical feel)
- **Badges/tags**: `4px`
- **Pills**: `9999px` (only for status badges)
- **Avatars**: `50%` (round)
- **Cards**: `8px`

### Button states
- **Default**: bg as specified, border 1px
- **Hover**: bg lightens by 1 step (e.g., gray-800 → gray-700)
- **Active/Pressed**: bg lightens by 2 steps
- **Disabled**: opacity 50%, cursor not-allowed
- **Focus**: ring-2 ring-blue-500/50 ring-offset-2

---

## 3. Colors (Dark Theme)

Primary palette for the dark medical imaging environment.

### Backgrounds
| Token | Tailwind | Hex | Usage |
|-------|----------|-----|-------|
| `bg-base` | `bg-gray-950` | `#030712` | App background |
| `bg-surface` | `bg-gray-900` | `#111827` | Cards, panels |
| `bg-elevated` | `bg-gray-800` | `#1F2937` | Dropdowns, modals, hovers |
| `bg-hover` | `bg-gray-700` | `#374151` | Hover states |

### Borders
| Token | Tailwind | Hex | Usage |
|-------|----------|-----|-------|
| `border-default` | `border-gray-700` | `#374151` | Standard borders |
| `border-subtle` | `border-gray-800` | `#1F2937` | Subtle dividers |

### Text
| Token | Tailwind | Hex | Usage |
|-------|----------|-----|-------|
| `text-primary` | `text-gray-50` | `#F9FAFB` | Headings, important text |
| `text-secondary` | `text-gray-300` | `#D1D5DB` | Body text |
| `text-muted` | `text-gray-400` | `#9CA3AF` | Labels, placeholders |
| `text-disabled` | `text-gray-500` | `#6B7280` | Disabled text |

### Accent colors
| Token | Tailwind | Hex | Usage |
|-------|----------|-----|-------|
| `accent` | `text-blue-500` | `#3B82F6` | Primary interactive |
| `accent-hover` | `text-blue-600` | `#2563EB` | Hover on accent |
| `success` | `text-emerald-500` | `#10B981` | Active, pass, online |
| `danger` | `text-red-500` | `#EF4444` | Destructive, errors |
| `warning` | `text-amber-500` | `#F59E0B` | Warnings, attention |

### Rule: No shadows in dark mode
Dark backgrounds make shadows invisible. Use **border** or **background
elevation** (lighter bg = higher elevation) instead of `shadow-*` classes.

---

## 4. Typography

| Token | Size | Weight | Line Height | Usage |
|-------|------|--------|-------------|-------|
| `text-xs` | 11px | 400 | 16px | Badges, timestamps, labels |
| `text-sm` | 13px | 400 | 20px | Secondary info, metadata |
| `text-base` | 14px | 400 | 20px | Body text, table cells |
| `text-md` | 16px | 500 | 24px | Emphasis, subtitles |
| `text-lg` | 18px | 600 | 28px | Section headings |
| `text-xl` | 20px | 600 | 28px | Panel/card titles |
| `text-2xl` | 24px | 700 | 32px | Page headings |

### Font weights
- **400 (Regular)**: Body text, descriptions
- **500 (Medium)**: Labels, emphasis, button text
- **600 (Semibold)**: Headings, section titles
- **700 (Bold)**: Page titles only. Never overuse.

### Font family
```css
font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI',
             system-ui, sans-serif;
```

---

## 5. Layout

### Header
| Component | Height | Background |
|-----------|--------|------------|
| App bar (Line 1) | **48px** fixed | `bg-gray-900/90 backdrop-blur` |
| Breadcrumb (Line 2) | **36px** fixed | `bg-gray-800/50` |

### Containers
- **Max content width**: 1280px (`max-w-7xl`)
- **Page padding**: 24px (`p-6`)
- **Card padding**: 16px (`p-4`)
- **Card border-radius**: 8px (`rounded-lg`)
- **Card border**: 1px solid `border-gray-700`

---

## 6. Component Patterns

### Header controls (theme, language, user)
All header controls MUST be:
- **Same height**: 36px (medium button size)
- **Same border-radius**: 6px
- **Same gap**: 4px between them
- **Vertically centered** in the 48px header bar

### Patient banner
- Background: `bg-gray-900` (surface level)
- Border-bottom only (no border-left, no rounded corners, no shadow)
- Avatar: 40px circle
- Patient name: `text-xl font-bold`
- Identifiers (MRN, DOB): `text-sm font-mono` in `bg-gray-800 rounded px-2 py-0.5`

### Breadcrumb
- Font: 12px / 400
- Separator: `>` via ChevronRight icon (12px)
- Current page: font-weight 500, text-gray-200
- Parent links: text-gray-400, hover text-blue-400
- Background: slightly darker than app bar (`bg-gray-800/50`)

### Tables
- Header: `text-xs font-semibold uppercase tracking-wider text-gray-400`
- Cells: `text-sm text-gray-300`
- Row hover: `bg-gray-800/50`
- Border: `border-gray-700/50` between rows

---

## 7. Anti-patterns (NEVER do these)

1. **Never use `shadow-lg` or `shadow-2xl` in dark mode** — invisible, adds nothing
2. **Never use `animate-pulse` on decorative elements** — distracting in clinical context
3. **Never mix button heights** — if one button is 36px, ALL adjacent buttons must be 36px
4. **Never use gradient text** (`bg-clip-text text-transparent`) for functional headings — reduces readability
5. **Never absolute-position action buttons** over content — use proper flex layout
6. **Never put page-specific actions in the app-level header** — each level owns its own actions
7. **Never use `blur-lg` decorative blobs** in clinical views — they consume GPU and add no clinical value
8. **Never hardcode colors** — always use the tokens above
9. **Never use more than 3 font weights on one screen**
10. **Never add a compliance badge (HIPAA, ISO) inside clinical workspace** — those belong on marketing/login pages only

---

## 8. Checklist Before Any UI Change

Before writing CSS/Tailwind, verify:

- [ ] Button height matches one of the 3 sizes (28/36/44px)
- [ ] Spacing uses 4px grid multiples
- [ ] Colors come from the token table (no arbitrary hex)
- [ ] Border-radius is 4/6/8px or 9999px (pills)
- [ ] Font size and weight match the typography scale
- [ ] No shadows in dark mode
- [ ] Controls at the same level have the same height
- [ ] The change follows the component patterns above
