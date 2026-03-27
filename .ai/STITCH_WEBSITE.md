# STITCH / WEBSITE / FRONTEND TASKS (STRICT)

These rules apply when Clogem is refining **UI-heavy** work (websites, landing pages, dashboards, HTML/CSS/JS frontends), especially after **Google Stitch** output or user-provided markup.

## Non-negotiables

- **Preserve intent**: Do not throw away layout, hierarchy, or component structure from the Stitch/UI source unless a review item explicitly requires it. Prefer **surgical** edits over wholesale redesign.
- **Production tone**: Avoid “toy” demos, placeholder lorem spam, or generic template aesthetics unless the task explicitly asks for a placeholder. If copy is unknown, use **concise, realistic** placeholder text (not repetitive Latin).
- **Semantic HTML**: Use landmarks (`header`, `nav`, `main`, `footer`, `section`) and heading levels that reflect outline order (`h1` → `h2` → `h3`).
- **Accessibility**: Every interactive control must be keyboard reachable with a visible `:focus` style. Do not remove focus outlines without replacing them. Prefer `button` for actions; use `a` for navigation. Associate `label` with inputs; describe errors in text (not color alone).
- **Responsive behavior**: Mobile-first CSS; no horizontal scroll on common viewports unless intentional (e.g. data tables with overflow). Test mentally at ~360px width: readable type, no overlapping tap targets.
- **Performance hygiene**: Prefer modern CSS (`grid`/`flex`, `clamp()` for type) over heavy JS. Defer non-critical JS; avoid blocking scripts in `<head>` without reason.
- **Security**: No inline `eval` of user strings. If forms exist, use safe patterns; do not embed secrets in client code.

## Visual system

- Establish a **small** palette (1–2 accents + neutrals) and a **type scale** (e.g. 3–4 steps). Do not invent random font sizes per section.
- Spacing must follow a **consistent rhythm** (e.g. 4/8/12/16px or a spacing scale via custom properties).
- Contrast: text/background pairs should meet common WCAG AA intent for body copy (treat seriously even if not formally measured).
- Avoid obvious “AI-made” visual signatures by default: neon gradient backgrounds, excessive glassmorphism, repetitive hero sections, identical card blocks across sections, and over-smoothed rounded corners everywhere.
- Do not default to overused AI stack fonts/themes unless asked (e.g. Inter/Poppins + generic startup gradient). Pick typography and accents based on product context and audience.
- If the user explicitly requests a font/theme/style, follow that request exactly (this rule overrides anti-template defaults).

## What to change vs what not to change

- **Change**: bugs, a11y gaps, inconsistent spacing, broken responsiveness, unclear hierarchy, missing alt text, fragile selectors.
- **Avoid**: renaming every class, reorganizing files, or swapping frameworks unless the task or review demands it.

## Output expectations (Codex)

- Return **only** code as per CODEX.md unless multi-file `FILE:` layout is required.
- When improving Stitch output, **start from the provided markup/CSS** and patch forward.
