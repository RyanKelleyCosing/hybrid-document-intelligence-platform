# `SurfaceMetricCard` consistency rules

`SurfaceMetricCard` (defined in
[review-app/src/components/SurfacePrimitives.tsx](../../review-app/src/components/SurfacePrimitives.tsx))
is the single primitive every public and admin surface uses to render an
"eyebrow + value + title + detail" tile. The card itself is layout-agnostic —
how the cards line up is decided by the **parent grid class**. This doc codifies
the round-7 layout patterns so future hero panels and metric strips stay
consistent and don't drift back to a generic `auto-fit, minmax(220px, 1fr)`
inside narrow containers.

## When to reach for which grid

| Context | Grid class | Columns | Notes |
| --- | --- | --- | --- |
| Page-level KPI strip below a hero (`/`, `/cost`, `/security`) | `metrics-grid` | `repeat(auto-fit, minmax(220px, 1fr))` | Wide parent (full content width). The default `auto-fit` is fine here because the container is never narrow. |
| Landing hero briefing drawer (right column on `/`) | `public-briefing-drawer-grid` | 2 columns × 2 rows, with the third card spanning both columns | Narrow column inside the hero. Do **not** use `auto-fit` — at 1440 px the cards collapse to a single column, breaking the 2-up rhythm. |
| Security hero status panel (right column on `/security`) | `security-status-grid` | 1-column stack of three subcards | Even narrower than the briefing drawer. A stack reads cleaner than a 2-up grid because the labels (Public / Sanitized / Private) are short titles, not metrics. |
| Generic mini-card grid in a section body | `workspace-card-grid` / `showcase-grid` | `auto-fit, minmax(220px, 1fr)` | Section-body width, full bleed. Safe to use the auto-fit default. |

## Hard rules

1. **Never put `repeat(auto-fit, minmax(220px, 1fr))` inside a hero panel.** Hero
   panels are bounded by `minmax(min(100%, 22rem), 1fr)` on the outer hero grid,
   so a 220 px tile minimum collapses to a single column at every desktop width.
   Use one of the explicit grid classes above instead.
2. **The card itself never sets its own width.** `SurfaceMetricCard` always
   renders with `surface-metric-card surface-card section-stack` plus whatever
   the caller passes in `className`. Width comes from the grid only.
3. **Order inside the card is fixed:** `badge → eyebrow → value → title →
   detail`. Don't reorder via CSS — change the props.
4. **Cards inside a hero panel must stay readable at 1024 px.** That is the
   narrowest viewport where the hero is still side-by-side. Below 1024 px the
   hero stacks and the panel takes full width, so the standard `auto-fit`
   defaults take over.
5. **Add a new grid class instead of overloading an existing one.** If a new
   surface needs different cardinality (e.g. four metrics in a hero), add
   `<surface>-status-grid` with explicit columns rather than tweaking
   `public-briefing-drawer-grid` to fit it.

## Where the rules are enforced today

- `review-app/src/styles.css`
  - `.metrics-grid` (page-level KPI strip)
  - `.public-briefing-drawer-grid` (landing hero, 2 + 1 spanning grid)
  - `.security-status-grid` (security hero, 1-column stack)
- `review-app/src/components/PublicLandingShell.tsx` — three `SurfaceMetricCard`
  instances inside `.public-briefing-drawer-grid`.
- `review-app/src/components/SecurityPostureSite.tsx` — three subcards inside
  `.security-status-grid`.
- `review-app/src/components/CostOverviewSite.tsx` and
  `review-app/src/components/PublicLandingShell.tsx` — KPI strips inside
  `.metrics-grid`.

## Checklist when adding a new metric card

- [ ] Pick a grid class from the table above based on the **parent container
      width**, not the page.
- [ ] If none fit, add a new `<surface>-status-grid` rule with explicit
      `grid-template-columns`. Do not reuse an existing class with a different
      visual rhythm.
- [ ] Confirm at 1024, 1440, and 2560 px that the cards do not collapse to a
      single column inside a hero panel.
- [ ] Pass content through props (`badge`, `eyebrow`, `value`, `title`,
      `detail`); do not inject custom children to fake an extra row.
