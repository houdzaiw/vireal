"""Synthetic offline regression: no secrets, database, deployment or HTTP."""

import copy
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from legacy_deploy_policy import (
    BLOCKER_ID,
    BLOCKER_SCRIPT,
    WORKFLOW_EVENTS,
    PolicyError,
    load_workflow,
    validate_repository,
    validate_workflow,
)

ROOT = Path(__file__).resolve().parents[2]


def workflows():
    for name in WORKFLOW_EVENTS:
        yield name, load_workflow((ROOT / ".github/workflows" / name).read_text())


class LegacyDeploymentGuards(unittest.TestCase):
    def test_actual_workflows_are_blocked(self):
        validate_repository(ROOT)

    def test_blocker_really_exits_nonzero_with_no_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                ["/bin/bash", "--noprofile", "--norc", "-e", "-c", BLOCKER_SCRIPT],
                cwd=directory,
                env={"PATH": os.defpath},
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("::error::Legacy deployment disabled.", result.stdout)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_true_missing_or_runtime_conditions_cannot_enable_deploy(self):
        for name, workflow in workflows():
            for condition in (
                None,
                True,
                0,
                "false",
                "true",
                "${{ true }}",
                "${{ false }}",
                "${{ inputs.authorized }}",
                "${{ vars.LEGACY_DEPLOY_ENABLED }}",
                "${{ github.repository != 'fastapi/full-stack-fastapi-template' }}",
                "${{ always() }}",
            ):
                with self.subTest(name=name, condition=condition):
                    changed = copy.deepcopy(workflow)
                    if condition is None:
                        changed["jobs"]["deploy"].pop("if")
                    else:
                        changed["jobs"]["deploy"]["if"] = condition
                    with self.assertRaises(PolicyError):
                        validate_workflow(name, changed)

    def test_deploy_cannot_drop_or_replace_failed_dependency(self):
        for name, workflow in workflows():
            for dependency in (None, [], "other-job", [BLOCKER_ID, "other-job"]):
                with self.subTest(name=name, dependency=dependency):
                    changed = copy.deepcopy(workflow)
                    if dependency is None:
                        changed["jobs"]["deploy"].pop("needs")
                    else:
                        changed["jobs"]["deploy"]["needs"] = dependency
                    with self.assertRaises(PolicyError):
                        validate_workflow(name, changed)

    def test_blocker_cannot_be_skipped_soft_failed_or_reusable(self):
        for name, workflow in workflows():
            for field, value in (
                ("if", "${{ false }}"),
                ("continue-on-error", True),
                ("env", {"SECRET_KEY": "${{ secrets.SECRET_KEY }}"}),
                ("environment", "production"),
                ("uses", "./.github/workflows/deploy.yml"),
            ):
                with self.subTest(name=name, field=field):
                    changed = copy.deepcopy(workflow)
                    changed["jobs"][BLOCKER_ID][field] = value
                    with self.assertRaises(PolicyError):
                        validate_workflow(name, changed)

    def test_blocker_cannot_become_a_success_or_execute_extra_steps(self):
        for name, workflow in workflows():
            for steps in (
                [],
                [{"run": "exit 0"}],
                [{"uses": "actions/checkout@main"}],
                workflow["jobs"][BLOCKER_ID]["steps"] + [{"run": "exit 0"}],
                [
                    {
                        "name": "Reject legacy deployment",
                        "shell": "bash",
                        "run": BLOCKER_SCRIPT + "true\n",
                    }
                ],
            ):
                with self.subTest(name=name, steps=steps):
                    changed = copy.deepcopy(workflow)
                    changed["jobs"][BLOCKER_ID]["steps"] = steps
                    with self.assertRaises(PolicyError):
                        validate_workflow(name, changed)

    def test_no_new_job_can_bypass_the_blocker(self):
        for name, workflow in workflows():
            changed = copy.deepcopy(workflow)
            changed["jobs"]["unguarded"] = {
                "runs-on": "self-hosted",
                "steps": [{"run": "exit 0"}],
            }
            with self.assertRaises(PolicyError):
                validate_workflow(name, changed)
            changed = copy.deepcopy(workflow)
            changed["jobs"].pop(BLOCKER_ID)
            with self.assertRaises(PolicyError):
                validate_workflow(name, changed)

    def test_deploy_cannot_add_tolerance_matrix_or_reusable_execution(self):
        for name, workflow in workflows():
            for field, value in (
                ("continue-on-error", True),
                ("strategy", {"matrix": {"target": ["production"]}}),
                ("uses", "./.github/workflows/other.yml"),
            ):
                with self.subTest(name=name, field=field):
                    changed = copy.deepcopy(workflow)
                    changed["jobs"]["deploy"][field] = value
                    with self.assertRaises(PolicyError):
                        validate_workflow(name, changed)

    def test_no_expanded_token_or_inherited_global_environment(self):
        for name, workflow in workflows():
            for field, value in (
                ("permissions", {"contents": "write"}),
                ("env", {"SECRET_KEY": "${{ secrets.SECRET_KEY }}"}),
            ):
                changed = copy.deepcopy(workflow)
                changed[field] = value
                with self.assertRaises(PolicyError):
                    validate_workflow(name, changed)
            changed = copy.deepcopy(workflow)
            changed["jobs"]["deploy"]["permissions"] = {"id-token": "write"}
            with self.assertRaises(PolicyError):
                validate_workflow(name, changed)

    def test_no_reactivation_through_new_dispatch_or_reusable_trigger(self):
        for name, workflow in workflows():
            for event in (
                {"workflow_dispatch": {"inputs": {"authorized": {"type": "boolean"}}}},
                {"workflow_call": None},
                {"pull_request_target": None},
                {"push": {"branches": ["main"]}},
            ):
                changed = copy.deepcopy(workflow)
                changed["on"] = event
                with self.assertRaises(PolicyError):
                    validate_workflow(name, changed)

    def test_ambiguous_duplicate_keys_and_merge_overrides_rejected(self):
        for text in (
            "jobs:\n  deploy:\n    if: '${{ false }}'\n    if: '${{ true }}'\n",
            "defaults: &job\n  if: '${{ false }}'\njobs:\n  deploy:\n    <<: *job\n    if: '${{ true }}'\n",
        ):
            with self.assertRaisesRegex(PolicyError, "duplicate_mapping_key"):
                load_workflow(text)

    def test_yaml_loader_does_not_change_global_safe_loader(self):
        self.assertIn("on", load_workflow("on:\n  workflow_dispatch:\n"))
        self.assertIn(True, yaml.safe_load("on:\n  workflow_dispatch:\n"))

    def test_original_repository_name_only_guard_is_rejected(self):
        for name, workflow in workflows():
            changed = copy.deepcopy(workflow)
            changed["jobs"].pop(BLOCKER_ID)
            changed["jobs"]["deploy"].pop("needs")
            changed["jobs"]["deploy"]["if"] = (
                "github.repository != 'fastapi/full-stack-fastapi-template'"
            )
            with self.assertRaises(PolicyError):
                validate_workflow(name, changed)

    def test_guard_runs_in_existing_precommit_ci_without_file_skips(self):
        config = load_workflow((ROOT / ".pre-commit-config.yaml").read_text())
        hooks = [
            hook
            for repo in config["repos"]
            for hook in repo["hooks"]
            if hook["id"] == "legacy-deploy-guards"
        ]
        self.assertEqual(len(hooks), 1)
        hook = hooks[0]
        self.assertIs(hook["always_run"], True)
        self.assertIs(hook["pass_filenames"], False)
        self.assertEqual(hook["language"], "unsupported")
        self.assertEqual(
            hook["entry"],
            "uv run python -I -B -m unittest discover -s tools/ci -p test_legacy_deploy_guards.py",
        )
        self.assertNotIn("files", hook)
        self.assertNotIn("stages", hook)
        workflow = load_workflow(
            (ROOT / ".github/workflows/pre-commit.yml").read_text()
        )
        self.assertIn("pull_request", workflow["on"])
        self.assertEqual(workflow["on"]["push"]["branches"], ["main"])
        self.assertNotIn("paths", workflow["on"]["push"])
        self.assertNotIn("paths-ignore", workflow["on"]["push"])

    def test_preserved_legacy_commands_stay_behind_disabled_job(self):
        legacy_steps = {
            "deploy.yml": ["uv run bash scripts/prestart.sh", "uv run fastapi deploy"],
            "deploy-docker-compose.yml": [
                "docker compose -f compose.yml -f compose.deploy.yml build",
                "docker compose -f compose.yml -f compose.deploy.yml run --rm backend bash scripts/prestart.sh",
                "docker compose -f compose.yml -f compose.deploy.yml up -d",
            ],
        }
        for name, workflow in workflows():
            validate_workflow(name, workflow)
            commands = [step.get("run") for step in workflow["jobs"]["deploy"]["steps"]]
            for expected in legacy_steps[name]:
                self.assertIn(expected, commands)


if __name__ == "__main__":
    unittest.main()
