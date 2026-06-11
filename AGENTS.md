# Wintoolbox Uninstall Benchmark — Custom Agents

## leaderboard-builder

**Purpose:** Specialized agent for building, designing, and optimizing the leaderboard site for the wintoolbox uninstall speedrun challenge.

**Expertise:**
- Building elegant static-site generators (Eleventy, Hugo, Jekyll, or refined Python + Jinja2)
- Modern leaderboard UI/UX (inspired by arena.ai, scale.com labs, and AI-native design patterns)
- Performance optimization (CSS, asset bundling, pagination, lazy loading)
- Data structure design and migration
- GitHub Pages deployment & CI/CD workflows
- Accessibility (a11y) and responsive design across devices
- Real-time leaderboard updates and dynamic features

**When to invoke:**
- Refactoring or improving the site generator (e.g., switching to SSG, adding new pages)
- Redesigning leaderboard layout, styling, or interactivity
- Adding features like search, filters, sorting, real-time updates, or analytics
- Optimizing performance or build time
- Setting up hosting, analytics, or CDN caching
- Implementing dark mode, animations, or micro-interactions
- Reviewing design against reference leaderboards (arena.ai, scale.com, etc.)

**Invocation example:**
```
runSubagent(
  agentName: "leaderboard-builder",
  prompt: "Migrate our current Python generator to Eleventy with Tailwind CSS for better style and performance. Keep data in data/*.json files."
)
```

---

## arena-ai-design-research

**Purpose:** Research and document the technology stack and design patterns used by arena.ai leaderboard and similar AI-native benchmark sites.

**Scope:**
- Analyze framework choices (frontend/backend), build tooling
- Document visual design language (colors, typography, spacing, animations)
- Extract reusable patterns and best practices
- Reference for styling and UX decisions

**Output:** Design decisions feed into SKILL files for the team.

