<!-- impeccable-product-context v1 -->
# Vireal product context

## Product

Vireal is a mobile-first AI video creation product. A user browses effect templates, uploads one or two portrait photos, chooses an available duration, spends coins, and receives an asynchronously generated video that remains accessible from their works history.

## Primary users

- Mobile H5 visitors who want a fast, visually led path from inspiration to generation.
- Signed-in creators who manage uploads, generation tasks, coin balance, purchases, and completed works.
- Operators who maintain categories, effects, prices, prompts, model routing, recommendations, ordering, status, and media assets from the existing admin application.

## Purpose and positioning

Vireal turns a browsable library of AI-motion effects into an operational creation flow. The public experience should feel like a premium visual catalogue while all availability, duration, cost, quota, balance, and task status values remain truthful backend data.

## Operating context

- Platform: responsive web, optimized first for mobile H5.
- Repositories: the existing `backend`, `frontend` admin, and `h5` applications under this project.
- Data: categories and effects are fully dynamic. A newly created category starts with three default effect records, while operators may add, delete, reorder, enable, or disable any number of effects.
- Media: operators upload covers and preview videos to the current object storage. Missing media uses the approved numbered gradient fallback.
- Generation: kiss and romance effects require two source images; other effects default to one. Supported durations, coin cost, model type, prompt, and recommendations are effect configuration.
- Compliance: adult authorization UI and backend validation are temporarily disabled, with reversible configuration and schema hooks retained.

## Core capabilities

- Browse six initially seeded first-level categories: kiss, romance, charm, outfit, dance, and anime.
- Open a specific effect and upload the required number of images.
- Select only backend-supported durations and see the corresponding actual coin cost.
- Submit a generation task, follow queue/progress/failure/success states, and inspect generated works.
- View actual remaining balance, quota, and available duration information.
- Maintain catalogue data and upload media through the admin application.

## Brand commitments

- `h5/outputs/vireal-wan-video-h5/prototype/prototype_v1.2.html` is the immutable visual baseline for this implementation; when it conflicts with older project UI, v1.2 wins.
- Preserve the dark Vireal catalogue world, compact cyan identity, horizontal category selector, cinematic effect cards, numbered gradient media fallback, and mobile-first composition.
- Do not retain prototype-only static commercial values. Real prices, balances, quotas, durations, and statuses must come from backend responses.
- Preserve current product functions even when the visual shell changes: authentication, uploads, generation, works, server-owned wallet, account, and admin operations. Existing app-store order APIs remain, but H5 payment is out of scope for v1.2.

## Product principles

1. Inspiration reaches a generatable effect in one tap.
2. Every value that affects a purchase or generation decision is sourced from backend data.
3. Missing media degrades deliberately; it never breaks the catalogue.
4. Required uploads are explicit before submission and validated again on the server.
5. Admin changes determine catalogue quantity and order without a frontend release.
6. Adult authorization can be restored by configuration and migration, not by rebuilding the flow.

## Accessibility and quality

- Primary actions and mobile controls target at least 44 CSS pixels.
- Keyboard focus remains visible and semantic buttons expose their state.
- Content remains usable under reduced motion, failed media, empty data, slow network, and insufficient-balance states.
- Responsive layouts avoid horizontal page overflow at 390 px and remain reviewable on desktop.

## Evidence

- Confirmed product requirements from the current agile PM workflow conversation.
- Visual authority: `h5/outputs/vireal-wan-video-h5/prototype/prototype_v1.2.html`.
- Data reference: `/Users/liqihui/Desktop/backend_data_v1.1.json`.
- Current implementation: `backend/`, `frontend/`, and `h5/` in this repository.
