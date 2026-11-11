"""Real loopback PostgreSQL TLS tests. Synthetic only; never connects to Neon."""

import importlib.util
import argparse
import datetime as dt
import ipaddress
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import psycopg
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def local_only(event, args):
    if event == "socket.connect":
        sock, address = args[:2]
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            if not ipaddress.ip_address(address[0]).is_loopback:
                raise RuntimeError("External network forbidden")


sys.addaudithook(local_only)
ROOT = Path(__file__).resolve().parents[2]
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
cluster = Path(tempfile.mkdtemp(prefix="vireal-tls-local.", dir="/tmp"))
cluster.chmod(0o700)
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
sockdir = cluster / "s"
sockdir.mkdir(mode=0o700)
env = {
    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    "LC_ALL": "C",
    "PYTHONDONTWRITEBYTECODE": "1",
}
report = {
    "synthetic_only": True,
    "target": "loopback only, temporary PostgreSQL 18",
    "cases": [],
    "remote_connections": 0,
    "cloud_changes": 0,
    "python_version": sys.version.split()[0],
    "psycopg_version": psycopg.__version__,
    "libpq_version": psycopg.pq.version(),
    "postgres_binary": subprocess.check_output(
        [str(pg / "postgres"), "--version"], text=True
    ).strip(),
}


def run(args, name):
    with (out / (name + ".log")).open("w") as stream:
        p = subprocess.run(
            [str(a) for a in args],
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            timeout=30,
        )
    if p.returncode:
        raise RuntimeError(name + " failed")


def key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


now = dt.datetime.now(dt.timezone.utc)


def name(cn):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


ca_key = key()
ca = (
    x509.CertificateBuilder()
    .subject_name(name("Synthetic Local CA"))
    .issuer_name(name("Synthetic Local CA"))
    .public_key(ca_key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - dt.timedelta(days=2))
    .not_valid_after(now + dt.timedelta(days=2))
    .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
    .sign(ca_key, hashes.SHA256())
)
server_key = key()


def cert(expired=False):
    return (
        x509.CertificateBuilder()
        .subject_name(name("localhost"))
        .issuer_name(ca.subject)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=2))
        .not_valid_after(
            now - dt.timedelta(days=1) if expired else now + dt.timedelta(days=1)
        )
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )


def pem(c):
    return c.public_bytes(serialization.Encoding.PEM)


ca_path = cluster / "ca.crt"
ca_path.write_bytes(pem(ca))
other_key = key()
other = (
    x509.CertificateBuilder()
    .subject_name(name("Other Synthetic CA"))
    .issuer_name(name("Other Synthetic CA"))
    .public_key(other_key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - dt.timedelta(days=1))
    .not_valid_after(now + dt.timedelta(days=1))
    .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
    .sign(other_key, hashes.SHA256())
)
other_path = cluster / "other.crt"
other_path.write_bytes(pem(other))
server_cert = cluster / "server.crt"
server_cert.write_bytes(pem(cert()))
server_private = cluster / "server.key"
server_private.write_bytes(
    server_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
)
server_private.chmod(0o600)
config = cluster / "tls.conf"


def config_text(ssl=True, old=False):
    return f"ssl = {'on' if ssl else 'off'}\nssl_cert_file = '{server_cert}'\nssl_key_file = '{server_private}'\nssl_min_protocol_version = '{'TLSv1.1' if old else 'TLSv1.2'}'\nssl_max_protocol_version = '{'TLSv1.1' if old else 'TLSv1.3'}'\npassword_encryption = 'scram-sha-256'\n"


def admin():
    return psycopg.connect(
        host=str(sockdir),
        port=port,
        dbname="postgres",
        user="postgres",
        autocommit=True,
    )


def reload():
    with admin() as c:
        c.execute("SELECT pg_reload_conf()")
    # Ensure a child backend sees updated settings before trying a new TLS session.
    expected = "on" if "ssl = on" in config.read_text() else "off"
    minimum = (
        "TLSv1.1"
        if "ssl_min_protocol_version = 'TLSv1.1'" in config.read_text()
        else "TLSv1.2"
    )
    for _ in range(30):
        with admin() as c:
            if (
                c.execute("SHOW ssl").fetchone()[0] == expected
                and c.execute("SHOW ssl_min_protocol_version").fetchone()[0] == minimum
            ):
                time.sleep(0.15)
                return
        time.sleep(0.1)
    raise RuntimeError("Reload not confirmed")


spec = importlib.util.spec_from_file_location(
    "reviewed_backup_reader", ROOT / "tools/operations/backup_once.py"
)
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


def protocol(c):
    return backup.negotiated_tls_protocol(c.pgconn)


params = dict(
    host="localhost",
    hostaddr="127.0.0.1",
    port=port,
    dbname="postgres",
    user="probe",
    password="SYNTHETIC-LOCAL-ONLY-NOT-A-REAL-CREDENTIAL",
    sslmode="verify-full",
    sslrootcert=str(ca_path),
    channel_binding="require",
    ssl_min_protocol_version="TLSv1.2",
    connect_timeout=3,
    options="-c default_transaction_read_only=on -c search_path=pg_catalog",
)


def check(label, allowed, **overrides):
    try:
        with psycopg.connect(**(params | overrides)) as c:
            c.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
            good = c.pgconn.ssl_in_use and protocol(c) in (b"TLSv1.2", b"TLSv1.3")
            row = c.execute(
                "SELECT current_database()='postgres', current_user='probe', session_user='probe', current_setting('transaction_read_only')='on', current_setting('transaction_isolation')='repeatable read', current_setting('search_path')='pg_catalog', ssl, version FROM pg_catalog.pg_stat_ssl WHERE pid=pg_catalog.pg_backend_pid()"
            ).fetchone()
            good = (
                good
                and row is not None
                and all(v is True for v in row[:7])
                and row[7] in ("TLSv1.2", "TLSv1.3")
            )
            backup.backend_tls(c)
            c.rollback()
            if not good:
                raise RuntimeError("Local evidence check failed")
        success = True
    except psycopg.OperationalError:
        success = False
    report["cases"].append(
        {
            "case": label,
            "expected_connect": allowed,
            "actual_connect": success,
            "passed": success == allowed,
        }
    )
    if success != allowed:
        raise RuntimeError("Unexpected result: " + label)


try:
    run(
        [
            pg / "initdb",
            "-D",
            cluster / "data",
            "-U",
            "postgres",
            "--auth-local=trust",
            "--auth-host=scram-sha-256",
            "--no-locale",
            "--encoding=UTF8",
        ],
        "tls-init",
    )
    config.write_text(config_text())
    with (cluster / "data/postgresql.conf").open("a") as f:
        f.write(f"\ninclude = '{config}'\n")
    run(
        [
            pg / "pg_ctl",
            "-D",
            cluster / "data",
            "-l",
            cluster / "server.log",
            "-o",
            f"-h 127.0.0.1 -k {sockdir} -p {port} -c unix_socket_permissions=0700",
            "-w",
            "start",
        ],
        "tls-start",
    )
    with admin() as c:
        c.execute(
            "CREATE ROLE probe LOGIN PASSWORD 'SYNTHETIC-LOCAL-ONLY-NOT-A-REAL-CREDENTIAL'"
        )
    check("trusted certificate plus matching host and required binding", True)
    check("wrong hostname", False, host="wrong.invalid")
    check("untrusted CA", False, sslrootcert=str(other_path))
    check("invalid password cannot authenticate", False, password="synthetic-wrong")
    server_cert.write_bytes(pem(cert(expired=True)))
    reload()
    check("expired server certificate", False)
    server_cert.write_bytes(pem(cert()))
    reload()
    check("valid certificate restored", True)
    config.write_text(config_text(old=True))
    reload()
    check("server restricted below TLS 1.2", False)
    config.write_text(config_text(ssl=False))
    reload()
    check("plaintext-only server", False)
    config.write_text(config_text())
    reload()
    hba = cluster / "data/pg_hba.conf"
    with hba.open("w") as f:
        f.write("local all all trust\nhost all all 127.0.0.1/32 trust\n")
    reload()
    check("TLS server with trust auth cannot satisfy required binding", False)
    report["exit_code"] = 0
except Exception as exc:
    report["exit_code"] = 1
    report["error_type"] = type(exc).__name__
finally:
    if (cluster / "data/postmaster.pid").exists():
        try:
            run(
                [pg / "pg_ctl", "-D", cluster / "data", "-m", "fast", "-w", "stop"],
                "tls-stop",
            )
        except Exception:
            report["stop_failed"] = True
    report["stopped"] = not (cluster / "data/postmaster.pid").exists()
    if report["stopped"]:
        shutil.rmtree(cluster)
    report["temporary_cluster_and_keys_removed"] = not cluster.exists()
    if not report["temporary_cluster_and_keys_removed"]:
        report["exit_code"] = 1
    report["qualification"] = (
        "Loopback driver behavior on this host only; not Neon internal encryption, a deployed endpoint, fresh backup or paid delivery."
    )
    (out / "local-tls-result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
sys.exit(report["exit_code"])
