# IntegrationLab appearance — Frosted Pearl and Graphite Glass

Approved direction. The earlier Dark OLED system in `design-system/integrationlab/MASTER.md` is historical.

## Themes

| Token | Light · Frosted Pearl | Dark · Graphite Glass |
| --- | --- | --- |
| Canvas | `#ECEEF2` | `#1C1C1E` |
| Content surface | `#FFFFFF` | `#2C2C2E` |
| Sidebar | translucent cool gray | translucent graphite |
| Text | `#1D1D1F` / `#6E6E73` | `#F5F5F7` / `#98989D` |
| Accent | `#0071E3` | `#0A84FF` |

Appearance is `system`, `light`, or `dark`. The choice is stored in `localStorage` under `integrationlab.appearance`. System follows `prefers-color-scheme`, including later OS changes. Operator credentials stay in `sessionStorage`.

A blocking script in `frontend/index.html` sets `data-theme` before first paint.

## Materials

Translucency is limited to the desktop sidebar and the top toolbar. Content groups, tables, dialogs, and the mobile drawer use solid surfaces. A zero count stays neutral. Danger and warning colors apply only when the count is greater than zero.

## Type

System UI stack. Monospace is for identifiers, code, and technical fields.
