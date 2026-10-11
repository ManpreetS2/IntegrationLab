# IntegrationLab UI Audit (pre-redesign)

## Current state

- Top-tab navigation in a centered `max-width: 1240px` shell
- Inter/system fonts; dark navy with a soft blue radial wash
- Shared `.panel`, `.summary-card`, tables, and status chips across pages
- Hash routing (`#/page?params`) and OperatorGate bearer unlock are sound

## Issues to fix

1. **Navigation** — Horizontal tabs crowd at ≤1024px; no persistent place-finding chrome
2. **Hierarchy** — Brand competes with page content; page titles are inconsistent (`h2` only)
3. **Density** — Large padding and uneven gaps waste ops-console space
4. **Tokens** — Colors hardcoded throughout `index.css`; no semantic status system
5. **Tables** — Readable but lack sticky header polish and consistent mono for IDs
6. **Empty/loading** — Functional via `SectionStatus` but visually flat
7. **Mobile** — No drawer; tabs wrap awkwardly
8. **Focus** — Limited visible focus rings on interactive controls

## Preserve

- All eight routes and hash deep links (`diagnostics?integration=`, `support?case=`)
- OAuth notice banner behavior
- Real vs SIMULATED evidence labeling
- Webhook Object/Amount wrapping fix
- API contracts and hooks (`useResource`, `useHashRoute`)

## Proposed structure

| Component | Role |
|-----------|------|
| `AppShell` | Sidebar + header + main |
| `Sidebar` / `MobileNav` | Eight routes, groups, env footer |
| `PageHeader` | Title, description, actions |
| Tokens in `:root` | Color, space, type, radius, shadow |
| Restyle existing panels/tables | Keep page business logic |

## Design direction (skill + product fit)

- **Style:** Dark Mode OLED + Data-Dense Dashboard
- **Type:** IBM Plex Sans (UI) + JetBrains Mono (IDs/metrics)
- **Accent:** Indigo/blue for actions; emerald/amber/red for health
- **Motion:** CSS 150–200ms only; honor `prefers-reduced-motion`
- **No** Tailwind/shadcn/GSAP/charts
