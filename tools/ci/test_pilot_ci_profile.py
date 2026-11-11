"""Validate the isolated qualification profile, including refused mutations."""

import copy
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / ".github/workflows/pilot-offline-acceptance.yml"
BRANCH = "codex/pilot-cost-bounds-20261111"
CHECKOUT = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
PYTHON = "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97"
UV = "astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9"
BUN = "oven-sh/setup-bun@0c5077e51419868618aeaa5fe8019c62421857d6"
OPTIONS = {
    CHECKOUT: {"fetch-depth": "0", "persist-credentials": "false"},
    PYTHON: {"python-version-file": ".python-version"},
    UV: {"version": "0.11.18", "enable-cache": "false"},
    BUN: {"bun-version": "1.4.0"},
}
RUNS = {
    "backend": [
        "uv sync --frozen",
        "uv run --no-sync python -I -B ../tools/ci/test_pilot_ci_profile.py",
        'uv run --no-sync python -I -B ../tools/ci/check_tls_loopback.py --pg-bin /usr/lib/postgresql/18/bin --output-dir "$RUNNER_TEMP/pilot-tls"',
        'uv run --no-sync python -I -B ../tools/ci/run_backend_offline.py --pg-bin /usr/lib/postgresql/18/bin --output-dir "$RUNNER_TEMP/pilot-backend"',
        "uv run --no-sync python -I -B ../tools/operations/test_local_tools.py",
        "uv run --project backend --no-sync python -m unittest discover -s tools/ci -p test_pilot_cost_bound.py -v",
        "uv run --project backend --no-sync python -m unittest discover -s tools/ci -p test_legacy_deploy_guards.py -v",
    ],
    "browser": [
        "bun ci",
        'bunx playwright install --with-deps "$BROWSER_PROJECT"',
        'python3 scripts/test-prelaunch-isolated.py --project "$BROWSER_PROJECT" --output-dir "$RUNNER_TEMP/pilot-browser"',
    ],
}


def validate(profile):
    """Only the reviewed branch, runners, commands and temporary storage apply."""

    def need(value):
        if not value:
            raise ValueError("UNREVIEWED_PILOT_CI_PROFILE")

    need(set(profile) == {"name", "on", "permissions", "concurrency", "jobs"})
    need(profile["name"] == "Pilot isolated acceptance")
    need(profile["on"] == {"push": {"branches": [BRANCH]}})
    need(profile["permissions"] == {"contents": "read"})
    need(
        profile["concurrency"]
        == {"group": "pilot-isolated-${{ github.ref }}", "cancel-in-progress": "false"}
    )
    need(set(profile["jobs"]) == {"backend", "browser"})
    for kind, job in profile["jobs"].items():
        keys = {"name", "runs-on", "timeout-minutes", "defaults", "steps"}
        if kind == "browser":
            keys |= {"needs", "strategy"}
            need(job["needs"] == "backend")
            need(
                job["strategy"]
                == {
                    "fail-fast": "false",
                    "matrix": {
                        "include": [
                            {"os": "ubuntu-24.04", "browser": "chromium"},
                            {"os": "macos-15", "browser": "webkit"},
                        ]
                    },
                }
            )
            need(job["runs-on"] == "${{ matrix.os }}")
            need(job["timeout-minutes"] == "15")
        else:
            need(job["runs-on"] == "ubuntu-26.04")
            need(job["timeout-minutes"] == "12")
        need(set(job) == keys)
        need(
            job["defaults"]
            == {"run": {"working-directory": "h5" if kind == "browser" else "backend"}}
        )
        uses, runs = [], []
        for step in job["steps"]:
            if "uses" in step:
                need(set(step) == {"uses", "with"})
                need(step["uses"] in OPTIONS)
                need(step["with"] == OPTIONS[step["uses"]])
                uses.append(step["uses"])
            else:
                need(set(step) <= {"run", "working-directory", "env"})
                command = step["run"]
                need(command in RUNS[kind])
                if "working-directory" in step:
                    need(
                        step["working-directory"] == "."
                        and "--project backend" in command
                    )
                if "env" in step:
                    need(step["env"] == {"BROWSER_PROJECT": "${{ matrix.browser }}"})
                    need(kind == "browser" and "BROWSER_PROJECT" in command)
                runs.append(command)
        need(uses == [CHECKOUT, PYTHON, BUN if kind == "browser" else UV])
        need(runs == RUNS[kind])
    return True


def validate_companion(events):
    if events != {
        "push": {"branches": ["main"]},
        "pull_request_target": {"types": ["synchronize"]},
    }:
        raise ValueError("UNREVIEWED_CONFLICT_COMMENT_TRIGGER")
    return True


class PilotCIProfile(unittest.TestCase):
    def setUp(self):
        self.profile = yaml.load(PROFILE.read_text(), Loader=yaml.BaseLoader)

    def refused(self, edit):
        changed = copy.deepcopy(self.profile)
        edit(changed)
        with self.assertRaises(ValueError):
            validate(changed)

    def test_reviewed_profile(self):
        self.assertTrue(validate(self.profile))

    def test_companion_does_not_comment_on_the_qualification_push(self):
        companion = yaml.load(
            (ROOT / ".github/workflows/detect-conflicts.yml").read_text(),
            Loader=yaml.BaseLoader,
        )
        self.assertTrue(validate_companion(companion["on"]))

    def test_unfiltered_companion_push_refused(self):
        with self.assertRaises(ValueError):
            validate_companion(
                {"push": "", "pull_request_target": {"types": ["synchronize"]}}
            )

    def test_pull_request_cannot_trigger(self):
        self.refused(lambda p: p["on"].update(pull_request={}))

    def test_paid_or_self_hosted_runner_refused(self):
        for runner in ("ubuntu-16-cores", "self-hosted"):
            with self.subTest(runner=runner):
                self.refused(lambda p: p["jobs"]["backend"].update({"runs-on": runner}))

    def test_artifact_upload_refused(self):
        self.refused(
            lambda p: p["jobs"]["backend"]["steps"].append(
                {"uses": "actions/upload-artifact@unreviewed", "with": {}}
            )
        )

    def test_persistent_cache_refused(self):
        self.refused(
            lambda p: p["jobs"]["backend"]["steps"][2]["with"].update(
                {"enable-cache": "true"}
            )
        )

    def test_write_token_refused(self):
        self.refused(lambda p: p["permissions"].update(contents="write"))

    def test_deployment_command_refused(self):
        self.refused(
            lambda p: p["jobs"]["backend"]["steps"][3].update(run="railway up")
        )

    def test_secret_environment_refused(self):
        self.refused(
            lambda p: p["jobs"]["backend"].update(env={"TOKEN": "${{ secrets.TOKEN }}"})
        )

    def test_matrix_expansion_refused(self):
        self.refused(
            lambda p: p["jobs"]["browser"]["strategy"]["matrix"]["include"].append(
                {"os": "macos-15-large", "browser": "webkit"}
            )
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
