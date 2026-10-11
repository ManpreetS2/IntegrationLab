# IntegrationLab macOS concepts (pending approval)

The previous `design-system/integrationlab/MASTER.md` (Dark OLED + data-dense dashboard) stays as history. It is not the source of truth for this pass.

## What the skill actually returned

Two `--design-system` runs were off-product and were **not** persisted:

1. `macos productivity developer tool minimal translucent` → Product Demo landing, Flat Design, teal `#0D9488` + orange CTA. Rejected: marketing page, no depth.
2. `developer observability dashboard light minimal` → FAQ landing, Dark OLED, green-on-navy. Rejected: this is the look the owner already disliked.

Verified domain hits that **do** apply:

- **Glassmorphism** (`styles.csv`): frosted blur for layered navigation. Use only on the sidebar and toolbar. Not on every content group. Contrast must stay ≥ 4.5:1.
- **Minimalism & Swiss Style**: whitespace, one accent, clear type hierarchy. The dataset also says “no shadows / radius 0”. That part is rejected for this product because Apple-like depth needs soft elevation and ~10–12px grouped corners.

Apple Human Interface Guidelines (Materials, Sidebars, Layout): separate navigation material from content, use translucency sparingly on the navigation layer, group related rows, and keep controls quieter than the status that needs attention.

## Concepts

| | A · Frosted Pearl | B · Graphite Glass |
|--|-------------------|--------------------|
| Canvas | `#ECEEF2` | `#1C1C1E` |
| Content groups | solid white | `#2C2C2E` |
| Navigation | frosted light sidebar | frosted graphite sidebar |
| Accent | `#0071E3` | `#0A84FF` |
| Type | system UI stack | same stack |
| Mono | IDs only | IDs only |

Dev-only route: `#/design-preview?concept=pearl|graphite`. It is not registered in production navigation. Fixture copy is labeled inside the preview.
