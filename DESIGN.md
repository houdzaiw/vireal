---
name: Vireal
description: A dark mobile-first AI motion catalogue that turns effect discovery into a truthful generation flow.
colors:
  ink-deep: "#020304"
  ink: "#090b0d"
  panel: "#151a1d"
  panel-raised: "#20272b"
  text: "#f7fbfc"
  muted: "#9caeb5"
  mist: "#b7f2ff"
  cyan: "#71d8ed"
  danger: "#ff9f9f"
  success: "#8cebc5"
  warning: "#ffd58f"
  line: "rgba(205, 239, 245, 0.15)"
typography:
  display:
    fontFamily: "PingFang SC, Microsoft YaHei, ui-sans-serif, system-ui, sans-serif"
    fontSize: "34px"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.035em"
  headline:
    fontFamily: "PingFang SC, Microsoft YaHei, ui-sans-serif, system-ui, sans-serif"
    fontSize: "25px"
    fontWeight: 650
    lineHeight: 1.08
    letterSpacing: "-0.03em"
  title:
    fontFamily: "PingFang SC, Microsoft YaHei, ui-sans-serif, system-ui, sans-serif"
    fontSize: "19px"
    fontWeight: 650
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  body:
    fontFamily: "PingFang SC, Microsoft YaHei, ui-sans-serif, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "normal"
  label:
    fontFamily: "PingFang SC, Microsoft YaHei, ui-sans-serif, system-ui, sans-serif"
    fontSize: "10px"
    fontWeight: 650
    lineHeight: 1.4
    letterSpacing: "0.08em"
rounded:
  sm: "12px"
  md: "14px"
  lg: "16px"
  full: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.mist}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "0 16px"
    height: "54px"
  button-secondary:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: "0 14px"
    height: "46px"
  input:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: "10px 12px"
    height: "44px"
  category-chip:
    backgroundColor: "rgba(183, 242, 255, 0.11)"
    textColor: "{colors.mist}"
    rounded: "{rounded.full}"
    padding: "0 16px"
    height: "44px"
---

# Design System: Vireal

## Overview

**Creative North Star: "The Midnight Motion Catalogue"**

Vireal presents AI video effects as a compact cinematic catalogue used primarily on a phone in low ambient light. The interface stays near-black so numbered covers and real preview media carry the emotion, while mist-cyan controls make state and action legible without turning the screen into a neon dashboard.

The system is operational beneath the atmosphere: upload requirements, duration, price, balance, quota, and task state are always explicit backend truth. Public H5 surfaces are immersive and dense; the admin surface translates the same vocabulary into a quieter, information-first workspace.

**Key Characteristics:**

- Near-black field with one cool mist accent.
- Media or intentional numbered fallback leads each public screen.
- Compact mobile hierarchy with 44px minimum interactive targets.
- Data-driven quantity, pricing, availability, and state.
- Inline SVG icons with a consistent light stroke.

## Colors

The palette is nocturnal and restrained: dark neutral fields create continuity while mist cyan is reserved for identity, selected state, and primary action.

### Primary

- **Mist Signal** (`#b7f2ff`): brand mark, selected category, primary action, focus ring, and positive interactive emphasis.
- **Motion Cyan** (`#71d8ed`): supporting accent and controlled luminous detail.

### Neutral

- **Night Field** (`#020304`): page background outside the application shell.
- **Catalogue Ink** (`#090b0d`): primary H5 canvas.
- **Operational Panel** (`#151a1d`): forms, lists, and secondary containers.
- **Raised Panel** (`#20272b`): generator and higher-priority operational surfaces.
- **Primary Text** (`#f7fbfc`): headings and essential content.
- **Secondary Text** (`#9caeb5`): explanatory copy and inactive navigation.
- **Quiet Line** (`rgba(205, 239, 245, 0.15)`): structural borders and separators.

### Status

- **Recovery Red** (`#ff9f9f`): failure and destructive state.
- **Completion Mint** (`#8cebc5`): success and active publication.
- **Attention Amber** (`#ffd58f`): warning and pending operator action.

### Named Rules

**The Truth Accent Rule.** Mist cyan highlights an actionable or truthful current state; it is not scattered as decoration.

## Typography

**Display Font:** PingFang SC with Microsoft YaHei and system sans fallbacks
**Body Font:** PingFang SC with Microsoft YaHei and system sans fallbacks

**Character:** Compact, direct, and neutral enough for bilingual content. Hierarchy comes from weight, size, and spacing instead of multiple font families.

### Hierarchy

- **Display** (700, 34px, 1): generation hero titles and major task states.
- **Headline** (650, 25px, 1.08): home promise and page-level mobile headings.
- **Title** (650, 19px, 1.2): generator panels and admin form sections.
- **Body** (400, 12px, 1.6): short H5 explanations; use 14–16px for longer reading surfaces.
- **Label** (650, 10px, 1.4): concise metadata, compact states, and measurements only.

### Named Rules

**The Compact Copy Rule.** Small type is limited to short labels and secondary facts; instructions and errors must remain readable without relying on capitalization or tracking.

## Layout

The H5 shell is mobile-first and fills the viewport below 760px. At larger widths it centers inside a 430px device frame. Public screens use 16px horizontal gutters, 12px card gaps, and 24px separation between major sections. The first effect spans both columns; subsequent effects form a two-column stream whose length is entirely data-driven.

The admin application uses a 232px sidebar and a flexible content column. Forms divide into a primary editing column and a 280px-or-wider preview column, collapsing to one column on narrow screens. Bottom H5 navigation always contains three equal destinations: Discover, Works, and Account.

## Elevation & Depth

Depth is mostly tonal. Panels step from ink to panel and raised-panel values with restrained translucent lines. Wide neutral-black shadows are reserved for the centered device shell, drawers, and surfaces that physically overlay another task. Colored zero-offset glows are not a general elevation token.

### Shadow Vocabulary

- **Device Ambient** (`0 30px 100px rgba(0, 0, 0, 0.75)`): desktop presentation of the H5 shell only.
- **Overlay Lift** (`0 28px 70px rgba(0, 0, 0, 0.58)`): modal drawer and protected-focus overlays.
- **Action Lift** (`0 10px 26px rgba(113, 216, 237, 0.20)`): primary generation action only.

**The Tonal-First Rule.** Use background value and a quiet border before adding a shadow.

## Shapes

Global operational controls and containers use 12–16px radii. Pills are reserved for categories, balance, and compact state chips. Circles are reserved for icon-only controls and avatars. The larger cinematic effect-card silhouette belongs to the Vireal H5 surface brief and is not a universal container rule.

## Components

### Buttons

- **Primary:** mist background, ink text, 54px height, 16px radius, and 44px-or-larger target.
- **Secondary:** dark panel or transparent background with a quiet line, 46px height, and 14px radius.
- **Focus:** 2px mist outline with 3px offset; focus is never communicated by color alone.
- **Disabled:** remove elevation and reduce contrast while keeping the label explicit about the missing requirement.

### Chips

- **Category chip:** 44px high pill, transparent when idle and mist-tinted with a mist border when selected.
- **Status chip:** compact state label whose foreground uses the relevant success, warning, or danger token.

### Cards / Containers

- **Operational cards:** panel surface, 12–16px corners, one quiet border, no decorative nested card stacks.
- **Effect media cards:** follow the H5 surface brief; use real cover or preview media first and the numbered gradient fallback only when media is absent or invalid.

### Inputs / Fields

- **Style:** ink background, quiet line, 12px radius, 44px minimum height.
- **Focus:** mist outline or border shift with visible caret.
- **Error:** recovery-red copy names the invalid field and the next action.

### Navigation

- **Top:** wordmark, live balance, and account control.
- **Category rail:** horizontally scrollable, touch-safe pills with one selected state.
- **Bottom:** Discover, Works, and Account only. Wallet is reached from the top balance or insufficient-balance recovery.

### Upload Slot

Dashed mist line at rest, solid mist line after upload, clear ordinal labels for dual-image effects, and independent retry or replacement per slot.

## Do's and Don'ts

### Do:

- **Do** preserve the external prototype as the visual authority for the H5 catalogue and generation screens.
- **Do** render every catalogue quantity and order from backend data.
- **Do** show current cost, balance, quota, available duration, and task state from API responses.
- **Do** fall back from preview video to cover and then to the numbered gradient treatment.
- **Do** keep public interactions at least 44px high and keep keyboard focus visible.

### Don't:

- **Don't** hard-code three visible effects; three is only the new-category seed count.
- **Don't** expose model prompts, storage keys, or internal provider secrets to the H5.
- **Don't** place Wallet or Coins in bottom navigation.
- **Don't** invent static prices, balances, quotas, or durations in production.
- **Don't** turn prototype-specific metadata labels, brand glow, or the text coin mark into general-purpose design-system decoration.
