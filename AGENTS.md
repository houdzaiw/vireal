# Project working agreement

- The fixed development branch is `codex/pilot-five-global-one-20261101` on `git@github.com:houdzaiw/vireal.git`.
- Continue all normal development on this existing branch. Do not create another branch or worktree unless the user explicitly requests or instructs it.
- The canonical local checkout is `/Users/huili/project/new-chat/work/vireal-ios-uikit`. The outer `/Users/huili/project/new-chat` Git repository and other old checkouts contain historical work and local operational records. Preserve them; do not accidentally commit or push from them.
- Before changes or pushes, confirm the current repository, branch, upstream and worktree status. Use ordinary pushes to the fixed branch. Do not force-push, merge to main, or deploy as an implication of committing code.
- Commit application source, native Xcode project and public configuration. Keep credentials, `.env`, `ios/Config/Local.xcconfig`, build products, device state, test output and operations receipts local.
- Web code is in `h5/`, backend in `backend/`, native Swift + UIKit client in `ios/`, and the original interactive prototype in `design/ios-prototype/`.
- A development push does not authorize a production release or opening registration, payments, uploads or paid generation. Follow the user's current deployment and integration instructions separately.

<!-- CODEGRAPH_START -->
## CodeGraph

If a `.codegraph/` directory exists at this repository root, use `codegraph_explore` or `codegraph explore` before text search to understand or locate code. Otherwise skip CodeGraph; do not create an index unless the user asks.
<!-- CODEGRAPH_END -->
