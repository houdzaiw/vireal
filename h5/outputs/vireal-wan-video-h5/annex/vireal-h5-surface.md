# Vireal H5 catalogue and generation surface

## Scope

Mode: Operate with an experience-led catalogue. Audience: mobile visitors and signed-in creators. Job: discover an effect, provide the required photos, understand the real cost and supported duration, submit once, and follow the result. Primary action: generate the selected effect. Proof: dynamic category/effect data, explicit upload requirements, real balance/cost/quota values, and visible task state. Constraints: preserve current product functions; hide adult authorization frontend and backend checks; external `prototype_v1.1.html` is the final visual authority; missing media must use its numbered gradient fallback.

## Chosen direction

The brief already pins a precise direction, so no concept round is needed. The home screen is a dark mobile catalogue with VIREAL identity, a horizontally scrollable category rail, and effects composed as one large lead tile followed by a compact two-column grid. The generation screen turns the selected tile into a cinematic header and an operational upload-and-purchase panel. Administrative views inherit the same data vocabulary but optimize for desktop maintenance.

## Direction contract

**THESIS** — A living AI-motion catalogue becomes the creation control itself. It refuses the prior generic marketing dashboard and the fixed “three template” assumption: every visible card is backed by an effect record, and the fallback treatment is an intentional cover rather than an empty state.

**OWN-WORLD** — Near-black ink fields, cool mist-cyan identity, restrained translucent borders, numbered cinematic gradients, compact uppercase metadata, and softly rounded controls. Public H5 stays dense and immersive; admin surfaces use the same cyan status language over a more legible operational canvas.

**STORY** — The visitor first sees a category already populated with usable effects, understands that card count is data-driven, opens one, sees exactly how many photos it needs, chooses a supported duration with its real price, then submits and follows a single durable task into works history.

**FIRST VIEWPORT** — At 390 px, the wordmark and live balance sit above a scrollable category rail. Category name and dynamic count lead directly into a tall first effect card, with no promotional hero separating intent from content. The card itself is the primary action; its number and title remain legible when media is absent.

**FORM** — Precisely specified replacement based on the user-pinned external prototype; no seed key applies. Signature interaction: a selected effect expands into the generation route while preserving its visual surface, then upload slots, duration, and real coin summary progressively enable the submit action. Motion is a single restrained surface drift and route transition, disabled under reduced motion.

**FINISH** — unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Prototype states

- Home with dynamic categories, arbitrary effect counts, and missing-media fallback.
- Generation with one-image and two-image variants, upload completeness, duration pricing, recommendations, insufficient balance, and task submission.
- Generation processing, success, and failure.
- Works empty and populated states; wallet/account/login continuity.
- Admin category/effect list and effect-edit states, including object-storage media upload placeholders.

## Unresolved until implementation

- Exact production API paths may follow existing FastAPI route conventions.
- Provider/model availability and duration-cost matrices remain operator data.
