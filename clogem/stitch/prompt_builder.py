"""Build a strong, structured prompt for Google Stitch from a vague user request."""

from __future__ import annotations

import re
from textwrap import dedent


def build_stitch_prompt(user_task: str) -> str:
    """
    Transform the user's task into a detailed Stitch-ready UI brief.
    Aims for production-quality, non-generic output (clear audience, IA, a11y, responsive).
    """
    raw = (user_task or "").strip()
    if not raw:
        raw = "A modern web experience with clear hierarchy and polished visuals."
    explicit_style = _has_explicit_style_request(raw)

    # Light extraction hints (best-effort; Stitch still interprets).
    product_hint = _first_line(raw)[:200]

    return dedent(
        f"""\
        ## Stitch UI brief (use as the full design prompt)

        ### Product / app
        {product_hint}

        ### Goal
        Produce a cohesive, production-quality UI (not a toy demo). The result should look like a real shipped product: intentional typography, spacing, and color—not a generic template.

        ### Target audience
        Primary users: describe briefly in your design choices (e.g. professionals, small-business owners, developers, students). Prefer a confident, trustworthy tone; avoid cliché “startup gradient on white” unless the brand explicitly asks for it.

        ### Information architecture
        - Define a clear primary action (CTA) per view.
        - Include sensible sections (e.g. hero, value props, social proof, pricing or FAQ if relevant, footer).
        - If a dashboard: include navigation, key widgets, empty states, and responsive collapse behavior.

        ### Visual direction
        - Establish a restrained palette (2–3 core colors + neutrals) and consistent type scale.
        - Use a clear grid; avoid random alignment.
        - Prefer subtle motion only if it aids comprehension (no gratuitous animation).
        - Make it feel designed by a human product team, not an AI template.
        - Avoid common AI-look defaults unless explicitly requested: neon purple/blue gradients, glassmorphism overload, oversaturated accent stacks, generic startup hero blocks, and repetitive rounded cards with identical shadows.
        - Prefer editorial restraint: meaningful whitespace, asymmetry where useful, nuanced contrast, and section-specific rhythm.
        - Avoid defaulting to overused AI fonts (e.g. Inter/Poppins everywhere) unless requested. Choose typography that matches the product domain and tone.
        - Use authentic visual hierarchy with varied component densities; do not make every section look cloned.

        ### Responsiveness
        - Mobile-first layout; readable line lengths; tap targets ≥ 44px where applicable.
        - Breakpoints: show how the layout adapts (stack → side-by-side where appropriate).

        ### Accessibility
        - Semantic HTML landmarks (header, main, nav, footer).
        - Visible focus states; sufficient color contrast; do not rely on color alone for meaning.
        - Form labels and error associations if forms exist.

        ### Components
        - Reusable patterns for buttons, cards, inputs, and navigation.
        - States: default, hover, active, disabled, loading/error where relevant.

        ### Deliverable
        Output clean, maintainable HTML/CSS (and minimal JS only if needed). Prefer modern CSS (flex/grid, custom properties). Avoid heavy frameworks unless the user asked for a specific stack.

        ### Style override rule
        {"User did not specify a font/theme. Choose a distinctive but production-safe style direction that avoids generic AI aesthetics." if not explicit_style else "User explicitly requested a style/font/theme. Honor that request exactly and do not override it with anti-template rules."}

        ### Original user request (verbatim context)
        {raw}
        """
    ).strip()


def _first_line(text: str) -> str:
    line = text.splitlines()[0].strip()
    return re.sub(r"\s+", " ", line)


def _has_explicit_style_request(text: str) -> bool:
    t = (text or "").lower()
    return bool(
        re.search(
            r"\b("
            r"font|typeface|typography|theme|style|brand|branding|palette|color scheme|"
            r"dark mode|light mode|minimalist|brutalist|glassmorphism|neumorphism|"
            r"material design|tailwind ui|use [a-z0-9 _-]+ font|use [a-z0-9 _-]+ theme"
            r")\b",
            t,
        )
    )
