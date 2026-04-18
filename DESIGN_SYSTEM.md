# MSTool-AI — Design System v2.0

> **MANDATORY**: Every UI change MUST reference this document before writing code.
> No ad-hoc styling. No arbitrary values. No exceptions.
>
> Last updated: 2026-04-18
>
> Sources: Nord Health Design System, NHS App Design System, Material Design 3,
> Radix Themes, Apple HIG, WCAG 2.2, OHIF Viewer, AHA Wristband Advisory,
> Manchester Triage System, Okabe-Ito colorblind-safe palette.

---

## 1. SPACING (4px base grid)

Every spacing value is a multiple of 4px. No arbitrary values allowed.

| Token | Value | Tailwind | Usage |
|-------|-------|----------|-------|
| `space-1` | 4px | `gap-1, p-1` | Icon-to-label gap |
| `space-2` | 8px | `gap-2, p-2` | Between related elements |
| `space-3` | 12px | `gap-3, p-3` | Normal element gap |
| `space-4` | 16px | `gap-4, p-4` | Card padding, section gap |
| `space-5` | 20px | `gap-5, p-5` | Comfortable padding |
| `space-6` | 24px | `gap-6, p-6` | Between sections |
| `space-8` | 32px | `gap-8, p-8` | Major content blocks |
| `space-12` | 48px | `p-12` | Page-level spacing |

---

## 2. BUTTONS

Three sizes. No exceptions. Every button on screen must be one of these.

| Size | Height | Padding | Font | Icon | Border Radius |
|------|--------|---------|------|------|---------------|
| **sm** | 28px | 4px 12px | 12px / 500 | 14×14 | 6px |
| **md** | 36px | 8px 16px | 13px / 500 | 16×16 | 6px |
| **lg** | 44px | 12px 20px | 14px / 600 | 18×18 | 6px |

### Icon-only buttons
Same height as text buttons. Square aspect ratio: 28×28, 36×36, 44×44.
Minimum touch target: 44×44px (Apple HIG / WCAG 2.5.8).

### Alignment rule
**If buttons are adjacent, ALL must be the same height.** Never mix sm + md.

### Button variants

| Variant | Background | Border | Text |
|---------|-----------|--------|------|
| **Primary** | `bg-blue-600` | none | white |
| **Secondary** | `bg-gray-800` | `border-gray-700` | `text-gray-200` |
| **Ghost** | transparent | none | `text-gray-400` |
| **Danger** | `bg-red-600/10` | `border-red-700/50` | `text-red-400` |

### Interaction states (apply to ALL buttons)

| State | Change |
|-------|--------|
| **Default** | As specified |
| **Hover** | Background lightens 1 step |
| **Active/Pressed** | Background lightens 2 steps, scale(0.98) |
| **Focus** | `ring-2 ring-blue-500/50 ring-offset-2 ring-offset-gray-900` |
| **Disabled** | `opacity-50 cursor-not-allowed pointer-events-none` |
| **Loading** | Spinner replaces icon, text changes to "Loading...", disabled |

---

## 3. COLORS

### 3a. Dark theme backgrounds (tonal elevation — no shadows)

| Token | Tailwind | Hex | Elevation | Usage |
|-------|----------|-----|-----------|-------|
| `bg-base` | `bg-gray-950` | `#030712` | Ground | App background |
| `bg-surface` | `bg-gray-900` | `#111827` | Level 1 | Cards, panels |
| `bg-elevated` | `bg-gray-800` | `#1F2937` | Level 2 | Dropdowns, modals |
| `bg-hover` | `bg-gray-700` | `#374151` | Level 3 | Hover states |
| `bg-active` | `bg-gray-600` | `#4B5563` | Level 4 | Active/pressed |

**Rule**: Higher elevation = lighter background. Never use `shadow-*` in dark mode.

### 3b. Light theme backgrounds

| Token | Tailwind | Hex | Usage |
|-------|----------|-----|-------|
| `bg-base` | `bg-gray-50` | `#F9FAFB` | App background |
| `bg-surface` | `bg-white` | `#FFFFFF` | Cards, panels |
| `bg-elevated` | `bg-gray-50` | `#F9FAFB` | Dropdowns, modals |
| `bg-hover` | `bg-gray-100` | `#F3F4F6` | Hover states |

### 3c. Borders

| Token | Dark | Light | Usage |
|-------|------|-------|-------|
| `border-default` | `#374151` (gray-700) | `#E5E7EB` (gray-200) | Standard |
| `border-subtle` | `#1F2937` (gray-800) | `#F3F4F6` (gray-100) | Dividers |
| `border-strong` | `#4B5563` (gray-600) | `#D1D5DB` (gray-300) | Emphasis |

**Width**: Always 1px. No 2px+ borders except focus indicators.

### 3d. Text

| Token | Dark hex | Light hex | Usage |
|-------|----------|-----------|-------|
| `text-primary` | `#F9FAFB` | `#111827` | Headings, names |
| `text-secondary` | `#D1D5DB` | `#4B5563` | Body, descriptions |
| `text-muted` | `#9CA3AF` | `#9CA3AF` | Labels, timestamps |
| `text-disabled` | `#6B7280` | `#D1D5DB` | Disabled elements |

### 3e. Accent / semantic colors

| Token | Hex | Usage |
|-------|-----|-------|
| `accent` | `#3B82F6` (blue-500) | Primary interactive, links |
| `accent-hover` | `#2563EB` (blue-600) | Hover on accent |
| `success` | `#10B981` (emerald-500) | Active, pass, stable |
| `danger` | `#EF4444` (red-500) | Destructive, critical, errors |
| `warning` | `#F59E0B` (amber-500) | Warnings, attention |
| `info` | `#0EA5E9` (sky-500) | Informational |

### 3f. Clinical status colors (AHA Wristband Advisory + Manchester Triage)

| Status | Color | Hex | Standard |
|--------|-------|-----|----------|
| **Immediate / Critical** | Red | `#DC2626` | Manchester Level 1, AHA allergy |
| **Very Urgent** | Orange | `#EA580C` | Manchester Level 2 |
| **Urgent / Warning** | Yellow | `#CA8A04` | Manchester Level 3, AHA fall risk |
| **Standard / Stable** | Green | `#16A34A` | Manchester Level 4 |
| **Non-urgent / Info** | Blue | `#2563EB` | Manchester Level 5 |
| **DNR / Special** | Purple | `#7C3AED` | AHA DNR |

### 3g. Data visualization (Okabe-Ito colorblind-safe palette)

For charts and graphs. Never rely on color alone — pair with shape/label.

| Name | Hex | Safe for |
|------|-----|----------|
| Orange | `#E69F00` | All types |
| Sky Blue | `#56B4E9` | All types |
| Bluish Green | `#009E73` | All types |
| Yellow | `#F0E442` | All types |
| Blue | `#0072B2` | All types |
| Vermillion | `#D55E00` | All types |
| Reddish Purple | `#CC79A7` | All types |

---

## 4. TYPOGRAPHY

| Token | Size | Weight | Line Height | Usage |
|-------|------|--------|-------------|-------|
| `text-2xs` | 10px | 400 | 14px | Micro labels (rare) |
| `text-xs` | 11px | 400 | 16px | Badges, timestamps |
| `text-sm` | 13px | 400 | 20px | Metadata, secondary info |
| `text-base` | 14px | 400 | 20px | Body text, table cells |
| `text-md` | 16px | 500 | 24px | Emphasis, subtitles |
| `text-lg` | 18px | 600 | 28px | Section headings |
| `text-xl` | 20px | 600 | 28px | Panel titles |
| `text-2xl` | 24px | 700 | 32px | Page headings |

### Font weights — usage rules
- **400**: Body text, descriptions, table cells
- **500**: Button labels, input labels, emphasis
- **600**: Section headings, card titles
- **700**: Page titles ONLY. Max 1 per screen.

### Font family
```css
font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
font-family-mono: 'JetBrains Mono', 'SF Mono', 'Fira Code', 'Consolas', monospace;
```

---

## 5. BORDER RADIUS

| Token | Value | Usage |
|-------|-------|-------|
| `radius-sm` | 4px | Badges, tags, inline elements |
| `radius-md` | 6px | Buttons, inputs, dropdowns |
| `radius-lg` | 8px | Cards, containers, panels |
| `radius-xl` | 12px | Modals, large containers |
| `radius-pill` | 9999px | Status pills, toggles |
| `radius-full` | 50% | Avatars, circular elements |

---

## 6. LAYOUT

### Fixed heights

| Component | Height | Background |
|-----------|--------|------------|
| App bar (header line 1) | **48px** | `bg-gray-900/90 backdrop-blur` |
| Breadcrumb bar (line 2) | **36px** | `bg-gray-800/50` |
| Patient banner | **auto** (min 64px) | `bg-gray-900` |
| Tab bar | **44px** | `bg-gray-800/60` |

### Content constraints
- Max content width: **1280px** (`max-w-7xl`)
- Page padding: **24px** (`p-6`)
- Card padding: **16px** (`p-4`)
- Sidebar width: **280px** (collapsible)

### Responsive breakpoints

| Name | Width | Columns | Usage |
|------|-------|---------|-------|
| `mobile` | < 640px | 1 | Phone |
| `tablet` | 640-1023px | 2 | iPad |
| `desktop` | 1024-1439px | 3-4 | Standard |
| `wide` | ≥ 1440px | 4-6 | Wide monitor |

---

## 7. MOTION / ANIMATION

### Durations

| Token | Value | Usage |
|-------|-------|-------|
| `duration-instant` | 50ms | Micro-interactions (checkbox, toggle) |
| `duration-fast` | 150ms | Hover effects, tooltips |
| `duration-normal` | 250ms | Panels, dropdowns opening |
| `duration-slow` | 400ms | Page transitions, modals |

### Easing curves

| Token | Value | Usage |
|-------|-------|-------|
| `ease-standard` | `cubic-bezier(0.2, 0, 0, 1)` | Most transitions |
| `ease-decelerate` | `cubic-bezier(0, 0, 0, 1)` | Elements entering |
| `ease-accelerate` | `cubic-bezier(0.3, 0, 1, 1)` | Elements exiting |

### Rules
- **Never** use `animate-pulse` on decorative elements in clinical views
- **Never** animate more than 2 properties simultaneously
- **Always** respect `prefers-reduced-motion` — disable animations when set
- Loading spinners: 800ms rotation, `ease-linear`

---

## 8. Z-INDEX SCALE

| Token | Value | Usage |
|-------|-------|-------|
| `z-base` | 0 | Normal content |
| `z-raised` | 10 | Cards above content |
| `z-dropdown` | 100 | Dropdowns, popovers |
| `z-sticky` | 200 | Sticky headers, sidebars |
| `z-overlay` | 300 | Overlay backgrounds |
| `z-modal` | 400 | Modal dialogs |
| `z-popout` | 500 | Tooltips, notifications |
| `z-toast` | 600 | Toast messages (always on top) |

---

## 9. FORMS

### Input fields

| Property | Value |
|----------|-------|
| **Height** | 36px (must match md button height) |
| **Padding** | 8px 12px |
| **Font** | 14px / 400 |
| **Border** | 1px solid `border-default` |
| **Border radius** | 6px (`radius-md`) |
| **Background** | `bg-gray-800` (dark) / `bg-white` (light) |
| **Placeholder** | `text-muted` |
| **Focus** | `ring-2 ring-blue-500/50`, border becomes `accent` |

### Input states

| State | Border | Background | Label |
|-------|--------|------------|-------|
| Default | `border-default` | `bg-surface` | `text-muted` |
| Focus | `accent` | `bg-surface` | `accent` |
| Error | `danger` | `bg-surface` | `danger` |
| Disabled | `border-subtle` | `bg-elevated` (dimmed) | `text-disabled` |

### Label rules
- Position: **always above** the input (never inline, never placeholder-only)
- Font: 12px / 500 / `text-muted`
- Spacing: 4px below label, 12px between fields
- Required: red asterisk `*` next to label
- Optional: gray "(optional)" text after label

### Error messages
- Position: below input, 4px gap
- Font: 12px / 400 / `danger`
- Icon: 14px warning icon before text
- Input gets: 1px left border in `danger` color

---

## 10. ACCESSIBILITY (WCAG 2.2 AA — mandatory)

### Contrast ratios

| Element | Minimum ratio | Check |
|---------|--------------|-------|
| Normal text (< 18px) | **4.5:1** | `text-primary` on `bg-surface` = 15.4:1 ✓ |
| Large text (≥ 18px or 14px bold) | **3:1** | All headings pass ✓ |
| UI components (borders, icons) | **3:1** | `border-default` on `bg-surface` = 3.2:1 ✓ |
| Focus indicator | **3:1** vs unfocused | Blue ring on dark = 4.1:1 ✓ |

### Focus indicators
- Style: `ring-2 ring-blue-500/50 ring-offset-2 ring-offset-gray-900`
- Minimum: 2px thick, 3:1 contrast
- **Never remove** `outline` without providing alternative focus indicator

### Touch targets
- Minimum: 24×24 CSS px (WCAG 2.5.8 AA)
- Recommended: 44×44px (Apple HIG / AAA)
- Spacing between targets: minimum 8px

### Keyboard navigation
- All interactive elements reachable via Tab
- Enter/Space activates buttons
- Escape closes modals/dropdowns
- Arrow keys navigate within menus/tabs

### Screen readers
- Every image/icon: `aria-hidden="true"` if decorative, `aria-label` if functional
- Breadcrumb: `<nav aria-label="Breadcrumb">` with `aria-current="page"`
- Alerts: `role="alert"` with `aria-live="polite"` (or `assertive` for critical)
- Loading states: `aria-busy="true"` on the loading container

---

## 11. COMPONENT PATTERNS

### Header (App bar)
```
Height: 48px
Background: bg-gray-900/90 backdrop-blur
Left:  [Logo 28×28] [gap-8] [App name text-sm/700]
Right: [Controls — ALL 36×36 buttons, gap-4 between them]
```

### Breadcrumb bar
```
Height: 36px
Background: bg-gray-800/50
Font: 12px / 400
Separator: ChevronRight 12×12, text-gray-600
Current page: 12px / 500, text-gray-200
Parent links: text-gray-400, hover → text-blue-400
Padding: 0 20px
```

### Patient banner
```
Background: bg-gray-900 (surface)
Border: bottom only, border-default
Padding: 16px 20px
Avatar: 40px circle, gradient, initials text-lg/700
Name: text-xl / 700 / text-primary
Identifiers: text-sm font-mono, inside bg-gray-800 rounded-sm px-8 py-2
Status badge: pill (radius-pill), text-xs/600 uppercase
```

### Cards
```
Background: bg-surface
Border: 1px border-default
Border radius: radius-lg (8px)
Padding: 16px
Hover: bg-elevated (if interactive)
NO shadows in dark mode
```

### Tables
```
Header: text-xs / 600 / uppercase / tracking-wider / text-muted
Cells: text-sm / 400 / text-secondary
Row hover: bg-elevated
Row border: border-subtle
Header bg: bg-elevated
Padding: 12px 16px
```

### Modals
```
Overlay: bg-black/60 backdrop-blur-sm
Container: bg-surface, radius-xl (12px), border-default
Max width: 560px (sm), 720px (md), 960px (lg)
Padding: 24px
Header: text-lg / 600, border-b, 16px padding-bottom
Footer: border-t, 16px padding-top, buttons right-aligned
Z-index: z-modal (400)
```

### Toast notifications
```
Position: bottom-right, 16px from edge
Background: bg-elevated
Border: 1px border-default
Border radius: radius-lg (8px)
Padding: 12px 16px
Font: text-sm / 500
Duration: 4s (info), 6s (warning), persistent (error)
Z-index: z-toast (600)
Animation: slide-up 250ms ease-decelerate
```

---

## 12. ANTI-PATTERNS (NEVER do these)

1. ❌ `shadow-lg` or `shadow-2xl` in dark mode → invisible, use border
2. ❌ `animate-pulse` on decorative elements → distracting in clinical context
3. ❌ Mix button heights in same row → all adjacent buttons same height
4. ❌ `bg-clip-text text-transparent` gradient text → poor readability
5. ❌ Absolute-position actions over content → use flex/grid layout
6. ❌ Page-specific actions in app-level header → each level owns its actions
7. ❌ Decorative blur blobs in clinical views → GPU waste, no clinical value
8. ❌ Hardcode colors outside this token table → always use tokens
9. ❌ More than 3 font weights on one screen → 400 + 500 + 600 max
10. ❌ Compliance badges (HIPAA/ISO) in clinical workspace → login/marketing only
11. ❌ `opacity` for disabled instead of proper disabled colors → use `text-disabled`
12. ❌ Remove `outline` on focus without alternative → violates WCAG 2.4.7

---

## 13. CHECKLIST (before ANY UI change)

- [ ] Button height is 28, 36, or 44px
- [ ] All adjacent buttons are the same height
- [ ] Spacing is a multiple of 4px
- [ ] Colors come from the token tables above
- [ ] Border-radius is 4, 6, 8, 12px or 9999px
- [ ] Font size and weight match the typography scale
- [ ] No shadows in dark mode (use border/bg elevation)
- [ ] Contrast ratio meets WCAG 2.2 AA minimums
- [ ] Focus indicator is visible (ring-2, 3:1 contrast)
- [ ] Touch targets are ≥ 24×24px (44×44 recommended)
- [ ] Input heights match button heights (36px)
- [ ] Labels are above inputs (never placeholder-only)
- [ ] Animations respect `prefers-reduced-motion`
- [ ] Clinical colors follow AHA/Manchester standards
- [ ] Chart colors use Okabe-Ito colorblind-safe palette
