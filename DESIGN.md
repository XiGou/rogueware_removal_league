# Design Notes

## Product Shape

Rogueware Removal League is a static competition directory for community-run rogueware removal challenges. Visitors should quickly answer:

1. What league projects exist?
2. Which project do I want to inspect or join?
3. Who is fastest on that project?
4. Is each run reviewable?

## Visual Direction

The interface combines:

- Scale Labs-style dense leaderboard presentation.
- Arena-style row comparability and rank clarity.
- OpenCode-style direct developer copy and low-friction static delivery.

The current visual language is a dark league sheet: warm charcoal surfaces, acid-green metric data, compact project cards, table-first rankings, and minimal motion.

## Layout

- Homepage: Rogueware Removal League directory with global stats, project cards, and project creation protocol.
- Project page: challenge title, per-project stats, paginated leaderboard, submission form, submission rules, and JSON example.
- Desktop leaderboard: table with stable columns for rank, runner, metric, steps, and proof.
- Mobile leaderboard: each table row becomes a stacked record with labels.
- Pagination: 50 submissions per page, generated as `index.html`, `page2.html`, and so on inside each project directory.

## Interaction

- Static HTML with a small client-side submission form that opens a prefilled GitHub Issue.
- External proof links open in a new tab.
- Focus states are visible.
- Motion is kept out of critical content loading.

## Accessibility

- Semantic headings and table markup.
- Skip links to project list or leaderboard.
- High-contrast text and controls.
- Mobile table labels are generated from `data-label` attributes.

## Implementation

- Generator: Python standard library in `generate_site.py`.
- Styles: vanilla CSS in `assets/style.css`.
- Projects: `data/projects.json`.
- Submissions: `data/submissions/<slug>/*.json`, one file per run.
- Deploy: GitHub Pages workflow in `.github/workflows/pages.yml`.
