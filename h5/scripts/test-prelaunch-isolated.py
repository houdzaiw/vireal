"""Existing local tools/browsers, synthetic build, loopback server, deny proxy."""

from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from collections import Counter
import argparse
import hashlib
import http.client
import json
import os
import platform
import signal
import subprocess
import threading
import shutil

H5 = Path(__file__).resolve().parents[1]
ROOT = H5.parent
parser = argparse.ArgumentParser()
parser.add_argument("--project", choices=("chromium", "webkit"))
parser.add_argument("--output-dir", required=True, type=Path)
args = parser.parse_args()
OUT = args.output_dir.resolve()
OUT.mkdir(parents=True, exist_ok=True)
DEPS = H5 / "node_modules"
BUN = shutil.which("bun")
assert BUN
report = {
    "started_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
    "synthetic_only": True,
    "new_software_installs": 0,
    "cloud_configuration_writes": 0,
    "real_payment_provider_or_email_calls": 0,
    "application_source_modified": False,
}
counts = Counter()


class Deny(BaseHTTPRequestHandler):
    def blocked(self):
        host = self.path.split("://", 1)[-1].split("/", 1)[0].split("@")[-1]
        counts[host] += 1
        self.send_response(403)
        self.end_headers()

    do_CONNECT = do_GET = do_POST = do_HEAD = blocked

    def log_message(self, *args):
        pass


proxy = ThreadingHTTPServer(("127.0.0.1", 0), Deny)
thread = threading.Thread(target=proxy.serve_forever, daemon=True)
thread.start()
assert DEPS.is_dir(), "Install the locked dependencies before starting this runner"
ENV = {
    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    "HOME": str(Path.home()),
    "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
    "LANG": "en_US.UTF-8",
    "CI": "1",
    "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD": "1",
    "VIREAL_API_BASE_URL": "https://api.example.com",
    "VITE_CLERK_PUBLISHABLE_KEY": "pk_test_ci_dummy",
    "OTEL_SDK_DISABLED": "true",
}


def run(args, name, timeout=120):
    with (OUT / (name + ".log")).open("w") as log:
        proc = subprocess.Popen(
            args,
            cwd=H5,
            env=ENV,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            return proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGINT)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=10)
            raise


try:
    assert not (ROOT / ".env").exists() and not (H5 / ".env").exists()
    candidate = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    assert len(candidate) == 40
    assert not subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True
    ).strip()
    report["candidate_commit"] = candidate
    ENV["VIREAL_RELEASE_COMMIT"] = candidate
    report["host_system"] = platform.system()
    report["host_release"] = platform.release()
    report["playwright_version"] = json.loads(
        (DEPS / "@playwright/test/package.json").read_text()
    )["version"]
    report["build_exit"] = run([BUN, "run", "build"], "build")
    assert report["build_exit"] == 0
    output = H5 / "dist/vireal-pages"
    index = (output / "index.html").read_text()
    assert (
        candidate in index
        and "https://api.example.com" in index
        and "pk_test_ci_dummy" in index
    )
    manifest = {
        "candidate_commit": candidate,
        "configuration": "SYNTHETIC ONLY, DO NOT DEPLOY",
        "files": {
            str(p.relative_to(output)): {
                "bytes": p.stat().st_size,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            }
            for p in sorted(output.rglob("*"))
            if p.is_file()
        },
    }
    (OUT / "build-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    probe = http.client.HTTPConnection("127.0.0.1", proxy.server_port, timeout=2)
    probe.request("GET", "http://synthetic.invalid/proxy-probe")
    answer = probe.getresponse()
    assert answer.status == 403
    answer.read()
    probe.close()
    proxy_url = "http://127.0.0.1:" + str(proxy.server_port)
    config = OUT / "isolated.config.ts"
    config.write_text(
        "import base from "
        + json.dumps(str(H5 / "playwright.prelaunch.config.ts"))
        + ";\nexport default {...base, testDir:"
        + json.dumps(str(H5 / "tests/browser"))
        + ", outputDir:"
        + json.dumps(str(OUT / "test-results"))
        + ', retries:0, maxFailures:1, globalTimeout:600000, reporter:[["json",{outputFile:'
        + json.dumps(str(OUT / "results.json"))
        + '}],["line"]], use:{...base.use,headless:true,proxy:{server:'
        + json.dumps(proxy_url)
        + ',bypass:"127.0.0.1,localhost"}}, webServer:{...base.webServer,cwd:'
        + json.dumps(str(H5))
        + "}};\n"
    )
    report["deny_proxy_configured"] = True
    report["static_server"] = "127.0.0.1:4182"
    report["contexts_service_workers"] = "block"
    command = [BUN, "run", "test:prelaunch", "--config=" + str(config)]
    if args.project:
        command.append("--project=" + args.project)
    report["test_exit"] = run(command, "browser-tests", timeout=660)
    if (OUT / "results.json").exists():
        report["stats"] = json.loads((OUT / "results.json").read_text()).get("stats")
    report["all_tests_passed"] = report["test_exit"] == 0
except Exception as exc:
    report["error_type"] = type(exc).__name__
    report["all_tests_passed"] = False
finally:
    proxy.shutdown()
    proxy.server_close()
    thread.join(timeout=3)
    report["deny_proxy_host_counts"] = dict(counts)
    report["deny_proxy_stopped"] = True
    report["finished_at"] = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
    report["working_tree_clean"] = not subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True
    ).strip()
    (OUT / "result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(report))

raise SystemExit(
    0 if report.get("all_tests_passed") and report.get("working_tree_clean") else 1
)
