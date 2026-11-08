"""Default-inert, one approved nontransactional email. Never auto-retry."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import signal
import sys
from datetime import UTC, datetime, timedelta

SENDER = "ops@alerts.usevireal.com"
RECIPIENT = "li522903183@gmail.com"
SUBJECT = "[TEST] Vireal 告警送达验收"
BODY = "这是一封非交易告警验收邮件。请在项目对话中确认实际收件时间。此邮件不涉及付款或生成。"
URL = "https://api.resend.com/emails"
READER = Path(
    "/Users/huili/project/new-chat/output/edge-production-backup-preparation-20261105/hidden_input.py"
)


def need(value):
    if not value:
        raise ValueError("SAFE_STOP")


def validate(grant, at):
    need(
        grant.get("authorized") is True
        and grant.get("operation") == "single-resend-test-email"
    )
    need(re.fullmatch("[a-f0-9]{12}", grant.get("run_id", "")))
    start, end = [datetime.fromisoformat(grant[k]) for k in ("starts_at", "expires_at")]
    need(
        start.tzinfo
        and end.tzinfo
        and start <= at < end <= start + timedelta(minutes=30)
    )
    need(
        grant["tool_sha256"] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    )
    need(grant.get("sender") == SENDER and grant.get("recipient") == RECIPIENT)
    # Account-wide remaining allowance must include ALL consumers, not only us.
    need(type(grant.get("remaining_daily")) is int and grant["remaining_daily"] >= 1)
    need(
        type(grant.get("remaining_monthly")) is int and grant["remaining_monthly"] >= 1
    )
    need(grant.get("sending_only_domain_restricted") is True)
    need(datetime.fromisoformat(grant["quota_verified_until"]) > at)
    need(grant["reader_sha256"] == hashlib.sha256(READER.read_bytes()).hexdigest())
    return end


def send(key, run_id, transport=None):
    import httpx
    import ssl

    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    with httpx.Client(
        verify=context,
        timeout=10,
        trust_env=False,
        follow_redirects=False,
        transport=transport,
    ) as client:
        reply = client.post(
            URL,
            headers={
                "Authorization": "Bearer " + key,
                "Idempotency-Key": "vireal-test-" + run_id,
            },
            json={"from": SENDER, "to": [RECIPIENT], "subject": SUBJECT, "text": BODY},
        )
        return reply.status_code in (200, 201, 202)


def execute(grant):
    end = validate(grant, datetime.now(UTC))
    need(
        sys.flags.isolated
        and sys.dont_write_bytecode
        and all(f.isatty() for f in (sys.stdin, sys.stdout, sys.stderr))
    )

    def expire(*_):
        raise TimeoutError("WINDOW")

    signal.signal(signal.SIGALRM, expire)
    signal.setitimer(
        signal.ITIMER_REAL, max(0.001, (end - datetime.now(UTC)).total_seconds())
    )
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.umask(0o077)
    root = Path.home() / "Documents/vireal-backups/email-acceptance"
    need(not root.is_symlink())
    root.mkdir(mode=0o700, exist_ok=True)
    need(root.stat().st_mode & 0o777 == 0o700)
    attempt = root / (grant["run_id"] + ".attempt.json")
    # Claim before input/I/O. Failed input and unknown send never reuse the ID.
    with attempt.open("x") as stream:
        json.dump({"state": "CLAIMED_NO_RETRY"}, stream)
    spec = importlib.util.spec_from_file_location("owner_hidden_reader", READER)
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    key = reader.hidden_input("唯一一项：仅发信且限定域的 Resend key")
    try:
        need(datetime.now(UTC) < end and re.fullmatch(r"re_[A-Za-z0-9_-]{10,200}", key))
        state = (
            "PROVIDER_ACCEPTED_NOT_RECEIPT"
            if send(key, grant["run_id"])
            else "NOT_ACCEPTED_NO_RETRY"
        )
    except Exception:
        state = "SEND_OUTCOME_UNKNOWN_NO_RETRY"
    finally:
        key = None
    with (root / (grant["run_id"] + ".result.json")).open("x") as stream:
        json.dump(
            {
                "state": state,
                "human_receipt_confirmed": False,
                "at": datetime.now(UTC).isoformat(),
            },
            stream,
        )
    signal.setitimer(signal.ITIMER_REAL, 0)
    print(state)
    return 0 if state == "PROVIDER_ACCEPTED_NOT_RECEIPT" else 2


if __name__ == "__main__":
    try:
        need(len(sys.argv) == 3 and sys.argv[1] == "--execute")
        raise SystemExit(execute(json.loads(Path(sys.argv[2]).read_text())))
    except (Exception, KeyboardInterrupt):
        print("邮件验收已停止 (SAFE_STOP_NO_RETRY)。")
        raise SystemExit(2) from None
