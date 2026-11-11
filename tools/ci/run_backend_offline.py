"""Disposable local acceptance: synthetic DB, Unix socket, network guard, no .env."""

import json
import os
import argparse
import sys
import xml.etree.ElementTree as ET
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlencode

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument("--pg-bin", required=True, type=Path)
parser.add_argument("--output-dir", required=True, type=Path)
args = parser.parse_args()
out = args.output_dir.resolve()
out.mkdir(parents=True, exist_ok=True)
pg = args.pg_bin.resolve()
assert subprocess.check_output(
    [str(pg / "postgres"), "--version"], text=True
).startswith("postgres (PostgreSQL) 18.")
python = sys.executable
cluster = Path(tempfile.mkdtemp(prefix="vireal-convergence-tests.", dir="/tmp"))
cluster.chmod(0o700)
sock = cluster / "s"
sock.mkdir(mode=0o700)
env = {
    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    "LC_ALL": "C",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
}
report = {
    "synthetic_only": True,
    "network_guard": "Rejects INET socket.connect and real HTTPX transports",
    "remote_database_connections": 0,
    "cloud_mutations": 0,
    "tests": [],
}


def run(args, name, extra=None, cwd=None, timeout=180):
    with (out / (name + ".log")).open("w") as stream:
        result = subprocess.run(
            [str(x) for x in args],
            env=extra or env,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
    return result.returncode


try:
    assert not (root / ".env").exists(), "Do not load real configuration"
    assert (
        run(
            [
                pg / "initdb",
                "-D",
                cluster / "data",
                "-U",
                "postgres",
                "--auth-local=trust",
                "--auth-host=reject",
                "--no-locale",
                "--encoding=UTF8",
            ],
            "init",
        )
        == 0
    )
    assert (
        run(
            [
                pg / "pg_ctl",
                "-D",
                cluster / "data",
                "-l",
                cluster / "postgres.log",
                "-o",
                f"-h '' -k {sock} -p 55489 -c unix_socket_permissions=0700",
                "-w",
                "start",
            ],
            "start",
        )
        == 0
    )
    assert (
        run(
            [pg / "createdb", "-h", sock, "-p", "55489", "-U", "postgres", "pilot"],
            "createdb",
        )
        == 0
    )
    testenv = {
        **env,
        "PYTHONPATH": str(root / "tools/ci/offline-network-guard")
        + ":"
        + str(root / "backend"),
        "ENVIRONMENT": "local",
        "FASTAPI_ENV": "development",
        "PROJECT_NAME": "PilotOfflineAcceptance",
        "DATABASE_URL": "postgresql://postgres@localhost/pilot?"
        + urlencode({"host": str(sock), "port": "55489"}),
        "SECRET_KEY": "SYNTHETIC-ISOLATED-SIGNING-ONLY-1234567890",
        "FIRST_SUPERUSER": "admin@example.com",
        "FIRST_SUPERUSER_PASSWORD": "SYNTHETIC-ADMIN-ONLY-1234567890",
        "EMAIL_TEST_USER": "test@example.com",
        "APP_IMAGE_STORAGE_BACKEND": "local",
        "LOCAL_UPLOAD_DIR": str(cluster / "media"),
        "PAYPAL_ENABLED": "false",
        "REPLICATE_ENABLED": "false",
        "OTEL_SDK_DISABLED": "true",
    }
    assert (
        run(
            [python, "-m", "alembic", "upgrade", "head"],
            "migrations",
            testenv,
            root / "backend",
        )
        == 0
    )
    targets = [
        "tests/services/test_operational_budget.py",
        "tests/services/test_storage.py",
        "tests/services/test_alert_limits.py",
        "tests/services/test_payment_webhook_verification.py",
        "tests/services/test_replicate_webhook.py",
        "tests/workers/test_video_tasks.py",
        "tests/api/routes/test_global_video_concurrency.py",
        "tests/api/routes/test_operational_controls.py",
        "tests/api/routes/test_paypal_commerce.py",
    ]
    targets = ["tests", "isolated_tests"]
    report["backend_exit"] = run(
        [
            python,
            "-m",
            "coverage",
            "run",
            "--data-file=" + str(out / "coverage"),
            "-m",
            "pytest",
            "-p",
            "anyio.pytest_plugin",
            "-q",
            "--tb=short",
            "--junitxml=" + str(out / "backend.xml"),
            *targets,
        ],
        "backend",
        testenv,
        root / "backend",
    )
    report["coverage_exit"] = run(
        [
            python,
            "-m",
            "coverage",
            "json",
            "--data-file=" + str(out / "coverage"),
            "--fail-under=90",
            "-o",
            out / "coverage-summary.json",
        ],
        "coverage",
        testenv,
        root / "backend",
    )
    if (out / "backend.xml").exists():
        report["test_count"] = len(
            ET.parse(out / "backend.xml").getroot().findall(".//testcase")
        )
    if (out / "coverage-summary.json").exists():
        report["coverage_percent"] = json.loads(
            (out / "coverage-summary.json").read_text()
        )["totals"]["percent_covered"]
except Exception as exc:
    report["error_type"] = type(exc).__name__
finally:
    if (cluster / "data/postmaster.pid").exists():
        report["stop_exit"] = run(
            [pg / "pg_ctl", "-D", cluster / "data", "-m", "fast", "-w", "stop"],
            "stop",
            timeout=30,
        )
    report["stopped"] = not (cluster / "data/postmaster.pid").exists()
    if report["stopped"]:
        shutil.rmtree(cluster)
    report["temporary_cluster_removed"] = not cluster.exists()
    (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))

sys.exit(
    0
    if report.get("backend_exit") == report.get("coverage_exit") == 0
    and report.get("temporary_cluster_removed")
    else 1
)
