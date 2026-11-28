"""Run native-login regressions on a disposable, socket-only local database."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlencode

parser = argparse.ArgumentParser()
parser.add_argument("--pg-bin", required=True, type=Path)
parser.add_argument("--repository", type=Path)
parser.add_argument("--output-dir", type=Path)
args = parser.parse_args()
runner_root = Path(__file__).resolve().parents[2]
root = args.repository.resolve() if args.repository else runner_root
out = (
    args.output_dir.resolve()
    if args.output_dir
    else runner_root / "ios/test-results/backend"
)
out.mkdir(parents=True, exist_ok=True)
assert not (root / ".env").exists(), "Use a clean checkout without live configuration"
cluster = Path(tempfile.mkdtemp(prefix="vireal-convergence-tests.", dir="/tmp"))
socket = cluster / "socket"
socket.mkdir(mode=0o700)
pg = args.pg_bin.resolve()
env = {
    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    "LC_ALL": "C",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
}
testenv = {
    **env,
    "PYTHONPATH": str(runner_root / "tools/ci/offline-network-guard")
    + ":"
    + str(root / "backend"),
    "ENVIRONMENT": "local",
    "FASTAPI_ENV": "development",
    "PROJECT_NAME": "NativeLoginOfflineTests",
    "DATABASE_URL": "postgresql://postgres@localhost/native?"
    + urlencode({"host": str(socket), "port": "55489"}),
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
report = {"synthetic_only": True, "remote_database_connections": 0}


def run(command, name, environment=env, cwd=None):
    with (out / (name + ".log")).open("w") as stream:
        subprocess.run(
            [str(x) for x in command],
            cwd=cwd,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
            check=True,
            timeout=180,
        )


try:
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
    run(
        [
            pg / "pg_ctl",
            "-D",
            cluster / "data",
            "-l",
            cluster / "postgres.log",
            "-o",
            f"-h '' -k {socket} -p 55489 -c unix_socket_permissions=0700",
            "-w",
            "start",
        ],
        "start",
    )
    run(
        [pg / "createdb", "-h", socket, "-p", "55489", "-U", "postgres", "native"],
        "createdb",
    )
    run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        "migrations",
        testenv,
        root / "backend",
    )
    run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "anyio.pytest_plugin",
            "-q",
            "--tb=short",
            "--junitxml=" + str(out / "results.xml"),
            "tests/services/test_clerk_auth.py",
            "tests/api/routes/test_app_clerk_auth.py",
            "tests/api/routes/test_staging_login_acceptance.py",
        ],
        "tests",
        testenv,
        root / "backend",
    )
    report["passed"] = True
except Exception as exc:
    report["passed"] = False
    report["error"] = type(exc).__name__
finally:
    if (cluster / "data/postmaster.pid").exists():
        run([pg / "pg_ctl", "-D", cluster / "data", "-m", "fast", "-w", "stop"], "stop")
    shutil.rmtree(cluster)
    report["temporary_cluster_removed"] = not cluster.exists()
    (out / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
sys.exit(0 if report.get("passed") else 1)
