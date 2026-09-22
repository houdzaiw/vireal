# Vireal Dual-Mode H5 Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Track progress with the checkboxes below.

**Goal:** Produce a reviewable v1.1 single-file Vireal H5 prototype that adds the approved compact standard/advanced mode switch, mode-aware duration rules, free-use copy, quota visibility, and clearly labelled local-demo results without overwriting v1.0.

**Architecture:** Copy the existing v1.0 single-file Tailwind prototype to v1.1 and extend its existing state, render, persistence, API, and event functions. Add a Python standard-library contract test suite that verifies the product-critical HTML/JavaScript contract without introducing a frontend toolchain. Stop at the product-prototype boundary; backend provider routing, quota enforcement, FFmpeg fallback, and deployment belong to the subsequent server implementation plan after this prototype and its flowcharts are approved.

**Tech Stack:** Static HTML, Tailwind CDN prototype styles, vanilla JavaScript, Python `unittest`, the existing Cloudflare Pages build script, the Impeccable detector, and manual browser QA.

## Scope and file map

Create:

- `outputs/vireal-wan-video-h5/prototype/prototype_v1.1.html`
- `tests/test_vireal_h5_prototype.py`

Modify:

- `scripts/build-vireal-pages.sh`
- `outputs/vireal-wan-video-h5/README.md`
- `outputs/vireal-wan-video-h5/PRD.md`

Do not modify:

- `outputs/vireal-wan-video-h5/prototype/prototype_v1.0.html`
- Any file inside the nested `server/` repository
- Production deployment configuration or live Cloudflare/Railway resources

The v1.1 prototype may express the approved future API contract by sending `mode`, but it must not be deployed against the current production API until the server implementation is complete.

## Task 1: Establish the versioned prototype and build contract

**Files:**

- Create: `tests/test_vireal_h5_prototype.py`
- Create: `outputs/vireal-wan-video-h5/prototype/prototype_v1.1.html`
- Modify: `scripts/build-vireal-pages.sh`

- [ ] **Step 1: Write failing baseline tests**

Create `tests/test_vireal_h5_prototype.py` with a small reusable loader and two baseline tests:

```python
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE = (
    ROOT
    / "outputs"
    / "vireal-wan-video-h5"
    / "prototype"
    / "prototype_v1.1.html"
)
BUILD_SCRIPT = ROOT / "scripts" / "build-vireal-pages.sh"


class VirealH5PrototypeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = PROTOTYPE.read_text(encoding="utf-8") if PROTOTYPE.exists() else ""
        cls.build_script = BUILD_SCRIPT.read_text(encoding="utf-8")

    def test_v11_prototype_exists(self) -> None:
        self.assertTrue(PROTOTYPE.exists())

    def test_pages_build_uses_v11(self) -> None:
        self.assertIn("prototype_v1.1.html", self.build_script)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the baseline tests and confirm the intended failure**

Run:

```bash
python3 -m unittest tests/test_vireal_h5_prototype.py -v
```

Expected: both tests fail because v1.1 does not exist and the build script still references v1.0.

- [ ] **Step 3: Create the versioned prototype without changing v1.0**

Run:

```bash
cp outputs/vireal-wan-video-h5/prototype/prototype_v1.0.html \
  outputs/vireal-wan-video-h5/prototype/prototype_v1.1.html
```

Edit `scripts/build-vireal-pages.sh` so its `source_file` points to `prototype_v1.1.html`.

- [ ] **Step 4: Run the baseline tests**

Run:

```bash
python3 -m unittest tests/test_vireal_h5_prototype.py -v
```

Expected: both tests pass.

- [ ] **Step 5: Commit the baseline**

```bash
git add tests/test_vireal_h5_prototype.py \
  outputs/vireal-wan-video-h5/prototype/prototype_v1.1.html \
  scripts/build-vireal-pages.sh
git commit -m "test: establish Vireal H5 v1.1 prototype"
```

## Task 2: Add the compact mode selector and duration rules

**Files:**

- Modify: `tests/test_vireal_h5_prototype.py`
- Modify: `outputs/vireal-wan-video-h5/prototype/prototype_v1.1.html`

- [ ] **Step 1: Add failing mode-contract tests**

Add these tests to `VirealH5PrototypeTests`:

```python
def test_compact_generation_mode_switch_exists(self) -> None:
    self.assertIn('id="generationModeSwitch"', self.html)
    self.assertIn('data-mode="standard"', self.html)
    self.assertIn('data-mode="advanced"', self.html)

def test_standard_mode_is_the_default(self) -> None:
    self.assertIn("mode: 'standard'", self.html)

def test_standard_mode_forces_five_seconds(self) -> None:
    self.assertIn("state.mode === 'standard'", self.html)
    self.assertIn("state.duration = 5", self.html)
    self.assertIn("duration10Button.disabled = isStandard", self.html)
```

- [ ] **Step 2: Run the tests and confirm they fail**

```bash
python3 -m unittest tests/test_vireal_h5_prototype.py -v
```

Expected: the three new tests fail because the selector and mode state do not exist.

- [ ] **Step 3: Add selector styling and accessible states**

In the existing `<style>` block, add styles for:

```css
.generation-mode-switch { /* compact two-option segmented control */ }
.generation-mode-btn { /* equal width, readable touch target */ }
.generation-mode-btn[aria-pressed="true"] { /* selected state */ }
.generation-mode-btn:focus-visible { /* keyboard focus ring */ }
.duration-option:disabled { /* visibly unavailable 10-second choice */ }
```

Use existing color, radius, type, and shadow tokens from v1.0. Do not introduce a new visual system.

- [ ] **Step 4: Insert the approved Step 3 mode control**

Place the selector immediately after the image-upload section:

```html
<section aria-labelledby="generationModeTitle">
  <div class="step-label">03</div>
  <h2 id="generationModeTitle">生成模式</h2>
  <div id="generationModeSwitch" class="generation-mode-switch" role="group" aria-label="生成模式">
    <button type="button" class="generation-mode-btn" data-mode="standard" aria-pressed="true">普通模式</button>
    <button type="button" class="generation-mode-btn" data-mode="advanced" aria-pressed="false">高级模式</button>
  </div>
  <p id="generationModeHint"></p>
</section>
```

Renumber duration to Step 4 and all following numbered sections consistently.

- [ ] **Step 5: Add state and rendering behavior**

Extend the existing state object with:

```javascript
mode: 'standard',
userRealRemaining: 5,
wanGlobalRemaining: 3,
```

Add `renderGenerationMode()` with these responsibilities:

```javascript
function renderGenerationMode() {
  const isStandard = state.mode === 'standard';
  if (isStandard) state.duration = 5;
  modeButtons.forEach((button) => {
    button.setAttribute('aria-pressed', String(button.dataset.mode === state.mode));
  });
  const duration10Button = [...durationButtons]
    .find((button) => Number(button.dataset.duration) === 10);
  duration10Button.disabled = isStandard;
  generationModeHint.textContent = isStandard
    ? '普通模式 · MiniMax · 固定约 5 秒'
    : '高级模式 · Wan · 可选 5 或 10 秒';
}
```

Use the actual collection shape already present in v1.0. The example deliberately locates the 10-second button with `find` over a spread `NodeList` rather than inventing an object index.

Bind one click listener per `[data-mode]` button. On change, update `state.mode`, call `renderGenerationMode()`, and then call the existing summary/button render functions.

- [ ] **Step 6: Run tests and commit**

```bash
python3 -m unittest tests/test_vireal_h5_prototype.py -v
git add tests/test_vireal_h5_prototype.py \
  outputs/vireal-wan-video-h5/prototype/prototype_v1.1.html
git commit -m "feat: add compact dual-mode H5 selector"
```

Expected: all tests pass.

## Task 3: Remove blocking consent and coin charging, then add disclosure and quota copy

**Files:**

- Modify: `tests/test_vireal_h5_prototype.py`
- Modify: `outputs/vireal-wan-video-h5/prototype/prototype_v1.1.html`

- [ ] **Step 1: Add failing disclosure and free-use tests**

```python
def test_upload_disclosure_is_non_blocking_and_complete(self) -> None:
    self.assertIn("上传即表示你拥有图片使用权", self.html)
    self.assertIn("第三方 AI 服务处理", self.html)
    self.assertIn("24 小时后清理", self.html)
    self.assertNotIn("if (!state.consent)", self.html)

def test_generation_does_not_spend_or_refund_demo_coins(self) -> None:
    self.assertNotIn("state.balance -= state.cost", self.html)
    self.assertNotIn("refundDemoCoins(task)", self.html)

def test_free_experience_summary_exists(self) -> None:
    self.assertIn('id="freeExperienceSummary"', self.html)
```

- [ ] **Step 2: Run tests and confirm failure**

```bash
python3 -m unittest tests/test_vireal_h5_prototype.py -v
```

Expected: new tests fail against the copied v1.0 behavior.

- [ ] **Step 3: Replace blocking consent with permanent upload disclosure**

Put this concise notice next to the uploader and keep it visible before selection:

```text
上传即表示你拥有图片使用权；图片可能由第三方 AI 服务处理。素材和作品将在 24 小时后清理。
```

Remove the blocking consent card, `state.consent`, its listener, its validation branch, and any consent modal binding. Preserve unrelated terms/privacy links.

- [ ] **Step 4: Replace coin UI with free quota UI**

Remove local coin deduction and refund behavior from generation. Replace the cost summary with:

```html
<div id="freeExperienceSummary" aria-live="polite"></div>
```

Render:

- `今日真实生成剩余 {userRealRemaining}/5`
- In advanced mode, also `高级模式全站剩余 {wanGlobalRemaining}/3`
- A free call-to-action label such as `免费生成视频`

Keep the existing balance elsewhere only if it is needed for historical prototype navigation; it must not affect the create flow.

- [ ] **Step 5: Run tests and commit**

```bash
python3 -m unittest tests/test_vireal_h5_prototype.py -v
git add tests/test_vireal_h5_prototype.py \
  outputs/vireal-wan-video-h5/prototype/prototype_v1.1.html
git commit -m "feat: make dual-mode prototype free to use"
```

Expected: all tests pass.

## Task 4: Express the mode-aware task API and restoration contract

**Files:**

- Modify: `tests/test_vireal_h5_prototype.py`
- Modify: `outputs/vireal-wan-video-h5/prototype/prototype_v1.1.html`

- [ ] **Step 1: Add failing API-contract tests**

```python
def test_idempotency_fingerprint_includes_mode(self) -> None:
    self.assertIn("dance:${state.mode}:${uploadId}:${state.duration}", self.html)

def test_video_task_request_sends_mode(self) -> None:
    self.assertIn("mode: state.mode", self.html)

def test_task_persists_execution_metadata(self) -> None:
    self.assertIn("executionType: payload.execution_type", self.html)
    self.assertIn("isDemo: Boolean(payload.is_demo)", self.html)

def test_demo_rendering_state_and_badge_exist(self) -> None:
    self.assertIn("rendering_demo", self.html)
    self.assertIn("payload.is_demo", self.html)
    self.assertIn('id="demoResultBadge"', self.html)
```

- [ ] **Step 2: Run tests and confirm failure**

```bash
python3 -m unittest tests/test_vireal_h5_prototype.py -v
```

- [ ] **Step 3: Make submission mode-aware**

Update the idempotency fingerprint to:

```javascript
const fingerprint = `dance:${state.mode}:${uploadId}:${state.duration}`;
```

Send this request body:

```javascript
{
  template_id: 'dance',
  mode: state.mode,
  upload_id: uploadId,
  duration: state.duration,
}
```

Standard mode always reaches this call with duration 5 because Task 2 enforces it.

- [ ] **Step 4: Persist enough task state to survive refresh**

Store these fields under the existing active-task storage key:

```javascript
{
  id: payload.id,
  idempotencyKey,
  mode: state.mode,
  duration: state.duration,
  executionType: payload.execution_type,
  isDemo: Boolean(payload.is_demo),
  fallbackReason: payload.fallback_reason || null,
  status: payload.status,
}
```

When polling, merge returned `execution_type`, `is_demo`, `fallback_reason`, `user_real_remaining`, and `wan_global_remaining` into state. Keep the existing rule that `submission_unknown` is terminal for automatic client behavior: show the error and never resubmit automatically.

- [ ] **Step 5: Add unified real/demo progress and result display**

Add `rendering_demo` to the progress-state mapping with copy such as `正在生成演示动画`.

Add a result badge above the existing player:

```html
<span id="demoResultBadge" hidden>演示结果</span>
```

Show it only when `payload.is_demo` or persisted `task.isDemo` is true. Both real and demo paths must use the same player, download action, works-card insertion, and 24-hour expiry copy.

- [ ] **Step 6: Run tests and commit**

```bash
python3 -m unittest tests/test_vireal_h5_prototype.py -v
git add tests/test_vireal_h5_prototype.py \
  outputs/vireal-wan-video-h5/prototype/prototype_v1.1.html
git commit -m "feat: support mode-aware video task states"
```

Expected: all tests pass.

## Task 5: Clarify bilingual mode, provider, and demo metadata

**Files:**

- Modify: `tests/test_vireal_h5_prototype.py`
- Modify: `outputs/vireal-wan-video-h5/prototype/prototype_v1.1.html`

- [ ] **Step 1: Add failing copy and metadata tests**

```python
def test_bilingual_mode_and_demo_labels_exist(self) -> None:
    for label in ("普通模式", "高级模式", "Standard", "Advanced", "演示结果", "Demo result"):
        self.assertIn(label, self.html)

def test_progress_copy_is_not_hard_coded_to_wan(self) -> None:
    self.assertNotIn("已提交到 Wan 视频生成队列", self.html)

def test_execution_label_helper_exists(self) -> None:
    self.assertIn("function executionLabel(task)", self.html)
    self.assertIn("local_demo", self.html)
```

- [ ] **Step 2: Run tests and confirm failure**

```bash
python3 -m unittest tests/test_vireal_h5_prototype.py -v
```

- [ ] **Step 3: Extend the existing translation dictionary**

Add Chinese and English keys for:

- Standard / 普通模式
- Advanced / 高级模式
- MiniMax real generation
- Wan real generation
- Demo result / 演示结果
- Daily personal quota
- Daily advanced global quota
- Free generation
- 24-hour retention

Route all new visible copy through the existing language render mechanism.

- [ ] **Step 4: Make progress and works metadata mode-aware**

Add:

```javascript
function executionLabel(task) {
  if (task.executionType === 'local_demo') return t('executionLocalDemo');
  if (task.mode === 'advanced') return t('executionWan');
  return t('executionMiniMax');
}
```

Use it in progress, result, and works cards. Add a small `Demo` badge to demo works while keeping the card layout shared.

For non-backend review mode, expose deterministic review actions for both real-result and demo-result states so product reviewers can inspect the player without a live provider call. Do not represent these actions as production controls.

- [ ] **Step 5: Run tests and commit**

```bash
python3 -m unittest tests/test_vireal_h5_prototype.py -v
git add tests/test_vireal_h5_prototype.py \
  outputs/vireal-wan-video-h5/prototype/prototype_v1.1.html
git commit -m "feat: clarify real and demo video results"
```

Expected: all tests pass.

## Task 6: Update prototype metadata, documentation, and Pages input

**Files:**

- Modify: `tests/test_vireal_h5_prototype.py`
- Modify: `outputs/vireal-wan-video-h5/prototype/prototype_v1.1.html`
- Modify: `outputs/vireal-wan-video-h5/README.md`
- Modify: `outputs/vireal-wan-video-h5/PRD.md`
- Verify: `scripts/build-vireal-pages.sh`

- [ ] **Step 1: Add failing version and documentation tests**

Extend the test loader with the README path and add:

```python
def test_v11_title_and_mode_review_route_exist(self) -> None:
    self.assertIn("Vireal · 双模式视频生成 v1.1", self.html)
    self.assertIn("mode: 'create'", self.html)

def test_readme_names_v11_as_current_prototype(self) -> None:
    readme = (
        ROOT / "outputs" / "vireal-wan-video-h5" / "README.md"
    ).read_text(encoding="utf-8")
    self.assertIn("prototype_v1.1.html", readme)
```

- [ ] **Step 2: Run tests and confirm failure**

```bash
python3 -m unittest tests/test_vireal_h5_prototype.py -v
```

- [ ] **Step 3: Update title and focused review routes**

Update the document title to `Vireal · 双模式视频生成 v1.1`.

Extend the prototype's focus-query handling with stable targets:

```text
prototype_v1.1.html?sandbox=true&focus=mode#create
prototype_v1.1.html?sandbox=true&focus=duration#create
prototype_v1.1.html?sandbox=true&focus=generation#create
```

Use `data-focus-zone="mode"`, `data-focus-zone="duration"`, and `data-focus-zone="generation"` on the corresponding sections. Preserve the existing `mode: 'create'` review-state convention.

- [ ] **Step 4: Update README and PRD status**

In `outputs/vireal-wan-video-h5/README.md`:

- Name v1.1 as the current review prototype.
- Name v1.0 as historical/reference-only.
- Document the three focused review URLs above.
- State that v1.1 must not be deployed until the matching backend contract is implemented.

In `outputs/vireal-wan-video-h5/PRD.md`:

- Record compact segmented option A under the prototype/design decision section.
- Mark the dual-mode H5 prototype as pending product review.
- Keep flowchart sections unfilled until the user approves v1.1.

- [ ] **Step 5: Run contract tests and the Pages build**

```bash
python3 -m unittest tests/test_vireal_h5_prototype.py -v
VIREAL_API_BASE_URL=https://api.usevireal.com bash scripts/build-vireal-pages.sh
```

Expected: tests pass; the build succeeds and its generated site uses v1.1 with the production API base injected.

- [ ] **Step 6: Verify v1.0 was not modified**

```bash
git diff --exit-code HEAD -- \
  outputs/vireal-wan-video-h5/prototype/prototype_v1.0.html
```

Expected: no output and exit code 0.

- [ ] **Step 7: Commit documentation and metadata**

```bash
git add tests/test_vireal_h5_prototype.py \
  outputs/vireal-wan-video-h5/prototype/prototype_v1.1.html \
  outputs/vireal-wan-video-h5/README.md \
  outputs/vireal-wan-video-h5/PRD.md \
  scripts/build-vireal-pages.sh
git commit -m "docs: publish Vireal dual-mode prototype v1.1"
```

## Task 7: Run bounded visual, responsive, and accessibility QA

**Files:**

- Modify if required: `outputs/vireal-wan-video-h5/prototype/prototype_v1.1.html`
- Modify if required: `tests/test_vireal_h5_prototype.py`

- [ ] **Step 1: Load the UI craft guidance before visual edits**

Read the complete execution-time craft-floor reference required by the installed Impeccable skill. This is an execution step, not a planning shortcut.

- [ ] **Step 2: Serve the prototype locally**

```bash
python3 -m http.server 5173 \
  --directory outputs/vireal-wan-video-h5/prototype
```

Open:

```text
http://localhost:5173/prototype_v1.1.html?sandbox=true&focus=mode#create
```

- [ ] **Step 3: Inspect the bounded review matrix**

Check each state at desktop width 1440 px and mobile width 390 px:

1. Standard selected: 5 seconds selected and 10 seconds disabled.
2. Advanced selected: 5 and 10 seconds both available.
3. Real result: provider/mode metadata visible and no demo badge.
4. Demo result: same player and actions, with `演示结果` badge.
5. English: labels, quota copy, and result metadata fit without clipping.

Also verify keyboard focus, `aria-pressed`, disabled semantics, touch target size, and readable contrast.

- [ ] **Step 4: Run the Impeccable detector exactly once after UI changes**

```bash
/Users/liqihui/.agents/skills/impeccable/scripts/impeccable detect --json \
  outputs/vireal-wan-video-h5/prototype/prototype_v1.1.html
```

Review the output and apply one bounded correction batch for material findings only. Do not begin open-ended visual polishing.

- [ ] **Step 5: Run final automated verification**

```bash
python3 -m unittest tests/test_vireal_h5_prototype.py -v
VIREAL_API_BASE_URL=https://api.usevireal.com bash scripts/build-vireal-pages.sh
git diff --check
```

Expected: all tests pass, build succeeds, and `git diff --check` produces no output.

- [ ] **Step 6: Capture final review evidence**

Capture one desktop screenshot and one 390 px mobile screenshot showing the mode selector and duration behavior. Include the review URLs and test output in the handoff.

- [ ] **Step 7: Commit any QA corrections**

Only if Step 4 or Step 5 required code changes:

```bash
git add tests/test_vireal_h5_prototype.py \
  outputs/vireal-wan-video-h5/prototype/prototype_v1.1.html
git commit -m "fix: polish Vireal dual-mode prototype"
```

## Completion checkpoint

Stop after Task 7 and present `prototype_v1.1.html` for Agile PM workflow Step 4 review. Do not deploy v1.1, modify the nested backend repository, create paid Replicate predictions, or begin the server implementation until the user approves the prototype and the subsequent flowcharts.
