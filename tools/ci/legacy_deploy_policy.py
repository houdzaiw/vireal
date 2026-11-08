"""Offline policy for retired deployment workflows; never runs deployment code."""

import argparse
import re
from pathlib import Path

import yaml

BLOCKER_ID = "legacy-deployment-blocked"
BLOCKER_SCRIPT = (
    'echo "::error::Legacy deployment disabled. '
    'Use the reviewed fixed-version release procedure."\n'
    "exit 1\n"
)
WORKFLOW_EVENTS = {
    "deploy.yml": {
        "push": {
            "branches": ["master"],
            "paths-ignore": ["release-notes.md"],
        },
        "workflow_dispatch": None,
    },
    "deploy-docker-compose.yml": {"workflow_dispatch": None},
}


class PolicyError(ValueError):
    """A fixed safety category, without workflow contents or credentials."""


class WorkflowLoader(yaml.SafeLoader):
    """Keep GitHub's 'on' key a string and reject ambiguous duplicate keys."""


# PyYAML's YAML 1.1 resolver otherwise treats the GitHub 'on' key as True.
WorkflowLoader.yaml_implicit_resolvers = {
    key: [(tag, pattern) for tag, pattern in entries if tag != "tag:yaml.org,2002:bool"]
    for key, entries in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
WorkflowLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|false|True|False|TRUE|FALSE)$"),
    list("tTfF"),
)


def unique_mapping(loader, node):
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        try:
            duplicate = key in result
        except TypeError as exc:
            raise PolicyError("invalid_mapping_key") from exc
        if duplicate:
            raise PolicyError("duplicate_mapping_key")
        result[key] = loader.construct_object(value_node)
    return result


WorkflowLoader.add_constructor("tag:yaml.org,2002:map", unique_mapping)


def load_workflow(text):
    try:
        workflow = yaml.load(text, Loader=WorkflowLoader)
    except yaml.YAMLError as exc:
        raise PolicyError("invalid_workflow_yaml") from exc
    if not isinstance(workflow, dict):
        raise PolicyError("workflow_mapping_required")
    return workflow


def validate_workflow(name, workflow):
    if name not in WORKFLOW_EVENTS:
        raise PolicyError("unknown_legacy_entry")
    allowed_top = {"name", "on", "permissions", "jobs"}
    if name == "deploy-docker-compose.yml":
        allowed_top.add("concurrency")
    if set(workflow) != allowed_top:
        raise PolicyError("unexpected_workflow_fields")
    if workflow["on"] != WORKFLOW_EVENTS[name]:
        raise PolicyError("legacy_events_changed")
    if workflow["permissions"] != {}:
        raise PolicyError("workflow_token_must_be_empty")
    jobs = workflow["jobs"]
    if not isinstance(jobs, dict) or set(jobs) != {BLOCKER_ID, "deploy"}:
        raise PolicyError("unexpected_legacy_jobs")
    blocker = jobs[BLOCKER_ID]
    if not isinstance(blocker, dict) or set(blocker) != {
        "name",
        "runs-on",
        "timeout-minutes",
        "permissions",
        "steps",
    }:
        raise PolicyError("blocker_fields_changed")
    if (
        blocker["name"] != "Legacy deployment blocked"
        or blocker["runs-on"] != "ubuntu-latest"
        or type(blocker["timeout-minutes"]) is not int
        or blocker["timeout-minutes"] != 1
        or blocker["permissions"] != {}
    ):
        raise PolicyError("blocker_settings_changed")
    if blocker["steps"] != [
        {"name": "Reject legacy deployment", "shell": "bash", "run": BLOCKER_SCRIPT}
    ]:
        raise PolicyError("blocker_must_only_fail")
    deploy = jobs["deploy"]
    allowed_deploy = {
        "if",
        "needs",
        "permissions",
        "runs-on",
        "timeout-minutes",
        "steps",
    }
    if name == "deploy-docker-compose.yml":
        allowed_deploy.add("env")
    if not isinstance(deploy, dict) or set(deploy) != allowed_deploy:
        raise PolicyError("deploy_fields_changed")
    if deploy["if"] is not False:
        raise PolicyError("deploy_must_remain_disabled")
    if deploy["needs"] != BLOCKER_ID:
        raise PolicyError("deploy_must_need_blocker")
    if deploy["permissions"] != {"contents": "read"}:
        raise PolicyError("deploy_permissions_changed")


def validate_repository(root):
    for name in WORKFLOW_EVENTS:
        workflow = load_workflow((root / ".github/workflows" / name).read_text())
        validate_workflow(name, workflow)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    args = parser.parse_args()
    try:
        validate_repository(args.root)
    except (PolicyError, OSError):
        parser.exit(
            1, "Legacy deployment policy rejected. No deployment was attempted.\n"
        )
    parser.exit(0, "Both legacy deployment entries are blocked.\n")


if __name__ == "__main__":
    main()
