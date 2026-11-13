# Legacy deployment guards

The two template-era deployment workflows are retained but cannot deploy:
`deploy.yml` (FastAPI Cloud and database prestart) and
`deploy-docker-compose.yml` (self-hosted Docker Compose and database prestart).
Their original triggers and deployment steps remain for reference.

Each workflow now has a credential-free, one-minute hosted job that prints a
fixed error and exits 1. The deployment job has a literal `if: false` condition
and depends on that failed job. There is no input or repository variable that can
enable it. Workflow permissions are empty; only the permanently disabled
deployment job retains its original read-only contents permission. The rejection
job does not check out source, read environment secrets, access a database or use
a self-hosted runner.

The explicit failure matters: GitHub reports a skipped job as successful, so an
all-skipped legacy workflow must not look like a completed release. These legacy
workflow checks are not among the six required source CI checks. See
[GitHub's job-condition documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-jobs-with-conditions).

Run the offline policy and regression suite from the repository root:

```bash
python -I -B tools/ci/legacy_deploy_policy.py
python -I -B -m unittest discover -s tools/ci -p test_legacy_deploy_guards.py
```

PyYAML is already in the locked backend standard dependencies; no new package or
version upgrade is needed. The existing pre-commit CI runs the regression on
every invocation, including changes outside the workflow paths. The suite only
parses local files, mutates public in-memory fixtures, and executes the fixed
rejection script with a minimal environment in a temporary directory. It never
executes the retained deployment commands or reads application configuration.

This patch is not an authorized release executor. Re-enabling either legacy
entry requires a separately reviewed code change and complete CI. Final Vireal
publication still requires the reviewed exact commit, explicit maintenance
authorization, correct targets and staged scope, unchanged TLS/identity/schema
gates, recovery safeguards, and API → Worker → H5 plus independent-monitor scope.
GitHub branch/environment protection and Railway/Pages auto-deployment changes
are separate online configuration work. They are neither applied nor claimed by
this local patch. Registration, recharge, upload and generation remain closed.

The guard only applies to revisions containing it. It cannot cancel an existing
run or change workflows at historical refs. Do not rerun old deployment runs or
dispatch an old ref. Separately review disabling both legacy workflows in GitHub
after this patch and CI are approved, alongside the online release protections.

## Offline capacity and cost arithmetic

`pilot_capacity_bound.py` counts opening/end captures conservatively, all
streams, extra captures and bounded failed/unknown attempts, without deletion
credit. It also sums explicitly bounded pool generations and non-application
connections, and computes CU-hours separately for each project. Unknown closing
duration, retry caps or other consumers raise `Unproven`; they are never zero.
These functions do not establish deployed limits or authorize an operation.
The actual provider quota, growth, memory/load and transfer evidence remain
separate gates. Current free storage already excludes existing files: do not
subtract them twice when deriving a per-file budget.

`pilot_cost_bound.py` accepts Standard R2 usage aggregated across the account
and separated by billing cycle. For storage, use cumulative daily account
peaks; phases sharing a day must not independently add the same peak. Use
`r2_cumulative_phase_costs` for the before/business-end/closing-end checkpoints.
It subtracts rounded cumulative costs within each cycle, then adds cycles.
Infrequent Access retrieval and minimum retention are outside this Standard
calculator. Unknown provider spending or future paid-balance/service liability
still blocks total-budget acceptance even when example arithmetic fits.

Run the pure, credential-free scenarios from the repository root:

```bash
python -B -m unittest discover -s tools/ci -p 'test_pilot_*bound.py'
```

No provider requests, live grants, configuration changes or new spending are
performed by these tests. Passing them is local arithmetic evidence, not
deployment, continuous backup, real capacity or promotion acceptance.
