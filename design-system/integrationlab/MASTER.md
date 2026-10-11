# Design System Master File

> **LOGIC:** When building a specific page, first check `design-system/pages/[page-name].md`.
> If that file exists, its rules **override** this Master file.
> If not, strictly follow the rules below.

---

**Project:** IntegrationLab
**Generated:** 2026-10-10
**Category:** Developer reliability / ops console (self-hosted)
**Design Dials:** Variance 4/10 | Motion 2/10 | Density 7/10
**Styles (UI/UX Pro Max):** Dark Mode OLED + Data-Dense Dashboard
**Stack constraint:** Custom CSS only — no Tailwind, shadcn, GSAP, or chart libraries

---

## Global Rules

### Color Palette

| Role | Hex | CSS Variable |
|------|-----|--------------|
| Background | `#0B0F17` | `--color-bg` |
| Sidebar | `#0E1420` | `--color-sidebar` |
| Surface / Card | `#121A27` | `--color-surface` |
| Surface elevated | `#172032` | `--color-surface-2` |
| Border | `#243044` | `--color-border` |
| Border strong | `#334155` | `--color-border-strong` |
| Foreground | `#E8EEF7` | `--color-fg` |
| Muted | `#8B9BB4` | `--color-muted` |
| Accent | `#4F7CFF` | `--color-accent` |
| Accent hover | `#3D6AE6` | `--color-accent-hover` |
| Accent muted bg | `rgba(79,124,255,0.12)` | `--color-accent-soft` |
| Healthy | `#3DCF8E` | `--color-ok` |
| Warning / simulated | `#E0A84A` | `--color-warn` |
| Failed / destructive | `#F07178` | `--color-danger` |
| Info / real source | `#6BB0E0` | `--color-info` |
| Focus ring | `#93B4FF` | `--color-ring` |

**Color notes:** Dark-first enterprise ops console. Accent is restrained indigo-blue (actions). Health uses emerald / amber / red with text labels — never color alone. Simulated evidence uses amber treatment distinct from real/info blue.

### Typography

- **UI / Body:** IBM Plex Sans
- **Mono / data:** JetBrains Mono (IDs, latencies, counts, code)
- **Google Fonts:** `IBM+Plex+Sans:wght@400;500;600;700` + `JetBrains+Mono:wght@400;500;600`

### Spacing (density 7)

| Token | Value |
|-------|-------|
| `--space-1` | `4px` |
| `--space-2` | `8px` |
| `--space-3` | `12px` |
| `--space-4` | `16px` |
| `--space-5` | `20px` |
| `--space-6` | `24px` |
| `--space-8` | `32px` |

### Layout

| Token | Value |
|-------|-------|
| `--sidebar-width` | `240px` |
| `--header-height` | `56px` |
| `--radius-sm` | `6px` |
| `--radius-md` | `8px` |
| `--radius-lg` | `10px` |
| `--content-max` | `1400px` |

### Motion

- Transitions: `150–200ms ease`
- Honor `prefers-reduced-motion: reduce`
- No decorative parallax, glow pulses, or marketing hero motion

### Shadows

| Token | Value |
|-------|-------|
| `--shadow-sm` | `0 1px 2px rgba(0,0,0,0.35)` |
| `--shadow-md` | `0 4px 12px rgba(0,0,0,0.35)` |

---

## Shell

- **Desktop:** Left sidebar (wordmark + 8 nav items in groups) + top page header (title, description, connectivity) + main content
- **Mobile:** Accessible drawer for navigation; hamburger with `aria-expanded` / focus trap basics
- Preserve hash routing (`#/page?params`)

### Nav groups

1. **Monitor** — Overview, Integrations
2. **Investigate** — Requests, Webhooks, Failures
3. **Resolve** — Diagnostics, Support Cases, Audit

---

## Components

- Panels: surface + 1px border, no heavy glass
- Metric cards: compact, tabular nums, status-tinted values
- Tables: sticky header optional, mono for IDs, horizontal scroll container
- Badges: text + color; SIMULATED always explicit
- Buttons: primary accent / secondary border / danger restrained
- Focus: visible 2px ring on interactive elements

---

## Pre-delivery checklist (skill)

- [x] Visible focus states
- [x] `prefers-reduced-motion`
- [x] Contrast on dark surfaces
- [x] Touch targets ≥ 40px on mobile nav
- [x] No hover-only critical actions
- [x] Responsive tables / no page-wide overflow
- [x] Status not color-only
- [x] Secrets never rendered
