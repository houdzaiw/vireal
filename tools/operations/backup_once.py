"""Owner-only single operating backup. Inert without a fresh explicit grant.

Reuses sealed R3 crypto/process/hidden-input code; never consumes a drill slot.
No plaintext is written. Credentials remain in memory; no restore or activation.
"""

import hashlib
import importlib.util
import json
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

OWNER = Path("/Users/huili/project/new-chat")
ENGINE = OWNER / "output/production-operating-backup-20261107.py"
ENGINE_SHA = "757ea509b321447176b612057991c5990c16085cd88c042713b59cc7e33e8b8f"
PROFILE_HEADS = {
    "production-26": ("6d3804e2c7cf6b8b1ad74091dde8ebaf9fc659c2", "c5d6e7f8a9b0", 26),
    "candidate-30": ("cb40c1c38c1ab4e9ea60063e8916dda083575417", "d6e7f8a9b0c1", 30),
    "candidate-33": ("d0728f31eac325430e0107c44aad5fae1f3151a9", "e7f8a9b0c1d2", 33),
}
EXTRA_TABLES = (
    "app_budget_window",
    "app_cost_observation",
    "app_cost_reservation",
    "app_operational_alert",
)


RESOURCE_TABLES = (
    "app_resource_policy",
    "app_resource_attempt",
    "app_media_read_grant",
)

SECURITY_MODES = ("native-postgres-tls", "neon-managed")
# Exact reviewed target is in the private profile, not public source.
PRODUCTION_TARGET_SHA256 = (
    "6527b3fd0c4d6ae12f8d7c03f2e69509158837b80202252a2d9df7b1da4c1713"
)
VENDOR_SOURCES = {
    "security.html": "https://neon.com/security",
    "connect-securely.html": "https://neon.com/docs/connect/connect-securely",
    "backup-pg-dump.html": "https://neon.com/docs/manage/backup-pg-dump",
}


def unique_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, "DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    return json.loads(raw, object_pairs_hook=pairs)


def production_target(target):
    return (
        type(target) is dict
        and set(target) == {"project", "host", "database", "role", "plan", "region"}
        and all(type(value) is str for value in target.values())
        and sha(json.dumps(target, sort_keys=True).encode()) == PRODUCTION_TARGET_SHA256
    )


def security_policy(grant, profile, at):
    """Validate an explicit, owner-bound policy before any credential input.

    Evidence hashes bind a human-reviewed vendor assertion, not a measurement
    of managed internal links. There is no fallback from native to managed.
    """
    mode = profile.get("security_mode")
    need(mode in SECURITY_MODES and grant.get("security_mode") == mode, "SECURITY_MODE")
    need(
        production_target(profile.get("target"))
        and grant.get("target") == profile["target"],
        "SECURITY_TARGET",
    )
    need("vendor_evidence_sha256" in grant, "SECURITY_EVIDENCE")
    if mode == "native-postgres-tls":
        need(
            grant["vendor_evidence_sha256"] is None
            and grant.get("vendor_evidence_path") is None,
            "SECURITY_EVIDENCE",
        )
        return {"security_mode": mode, "vendor_evidence_sha256": None}
    digest = grant["vendor_evidence_sha256"]
    need(
        isinstance(digest, str) and re.fullmatch("[0-9a-f]{64}", digest),
        "SECURITY_EVIDENCE",
    )
    path = Path(grant["vendor_evidence_path"])
    need(
        path.is_file() and not path.is_symlink() and path.stat().st_size <= 32768,
        "SECURITY_EVIDENCE",
    )
    raw = path.read_bytes()
    need(sha(raw) == digest, "SECURITY_EVIDENCE_PIN")
    evidence = unique_json(raw)
    need(
        evidence["schema"] == 1
        and evidence["target"] == profile["target"]
        and evidence["vendor_control_acceptance"] == "accepted-managed-trust-boundary"
        and evidence["known_public_exclusions"] == []
        and evidence["independently_verified_internal_hops"] is False
        and evidence["project_specific_confirmation"] == "not_obtained",
        "SECURITY_EVIDENCE_SCOPE",
    )
    start = datetime.fromisoformat(grant["starts_at"])
    reviewed = datetime.fromisoformat(evidence["reviewed_at"])
    need(
        reviewed.tzinfo and start - timedelta(minutes=30) <= reviewed <= start <= at,
        "SECURITY_REVIEW_WINDOW",
    )
    sources = evidence["sources"]
    need(
        type(sources) is dict and sources.keys() == VENDOR_SOURCES.keys(),
        "SECURITY_SOURCES",
    )
    for name, url in VENDOR_SOURCES.items():
        item = sources[name]
        fetched = datetime.fromisoformat(item["retrieved_at"])
        source = path.parent / name
        need(
            item["url"] == url
            and fetched.tzinfo
            and reviewed - timedelta(days=1) <= fetched <= reviewed
            and source.is_file()
            and not source.is_symlink()
            and source.stat().st_size <= 2 * 1024 * 1024
            and sha(source.read_bytes()) == item["sha256"],
            "SECURITY_SOURCE_PIN",
        )
    return {"security_mode": mode, "vendor_evidence_sha256": digest}


def profile_extra_tables(mode):
    need(mode in PROFILE_HEADS, "PROFILE")
    if mode == "production-26":
        return ()
    if mode == "candidate-30":
        return EXTRA_TABLES
    return (*EXTRA_TABLES, *RESOURCE_TABLES)


def need(value, code):
    if not value:
        raise ValueError(code)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def due_time(first, index, at):
    need(type(index) is int and index >= 0, "SCHEDULE")
    due = first + timedelta(minutes=45 * index)
    need(due - timedelta(minutes=4) <= at < due + timedelta(minutes=2), "SLOT_WINDOW")
    return due


def negotiated_tls_protocol(pgconn):
    """Read the actual connection protocol; unsupported drivers fail closed.

    psycopg-binary 3.3 exposes pgconn_ptr but not ssl_attribute. Load only its
    own bundled libpq, never a guessed system library with a foreign pointer.
    This function does not open a connection or change any TLS policy.
    """
    reader = getattr(pgconn, "ssl_attribute", None)
    if callable(reader):
        return reader(b"protocol")
    import ctypes

    from psycopg import pq

    need(type(pgconn) is pq.PGconn and pq.__impl__ == "binary", "CLIENT_TLS_DRIVER")
    import psycopg_binary

    package = Path(psycopg_binary.__file__).resolve().parent
    if sys.platform == "darwin":
        libraries = list((package / ".dylibs").glob("libpq.*.dylib"))
    elif sys.platform.startswith("linux"):
        libraries = list((package.parent / "psycopg_binary.libs").glob("libpq-*.so.*"))
    else:
        libraries = []
    need(len(libraries) == 1, "CLIENT_TLS_DRIVER")
    native = ctypes.CDLL(str(libraries[0]))
    native.PQlibVersion.restype = ctypes.c_int
    need(native.PQlibVersion() == pq.version(), "CLIENT_TLS_DRIVER")
    pointer = pgconn.pgconn_ptr
    need(isinstance(pointer, int) and pointer > 0, "CLIENT_TLS_DRIVER")
    native.PQsslAttribute.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    native.PQsslAttribute.restype = ctypes.c_char_p
    # Keep the native handle alive until the returned C string has been copied.
    protocol = native.PQsslAttribute(pointer, b"protocol")
    need(isinstance(protocol, bytes), "CLIENT_TLS_PROTOCOL")
    return protocol


def backend_tls(db, *, security_mode="native-postgres-tls", target=None):
    need(security_mode in SECURITY_MODES, "SECURITY_MODE")
    if security_mode == "neon-managed":
        need(production_target(target), "SECURITY_TARGET")
    need(db.pgconn.ssl_in_use, "CLIENT_TLS")
    protocol = negotiated_tls_protocol(db.pgconn)
    need(
        protocol in (b"TLSv1.2", b"TLSv1.3"),
        "CLIENT_TLS_PROTOCOL",
    )
    # get_parameters() omits values equal to libpq defaults, including TLS1.2.
    # Read only these public options from effective conninfo; never passwords.
    wanted = {
        b"sslmode",
        b"channel_binding",
        b"ssl_min_protocol_version",
        b"sslrootcert",
    }
    params = {
        item.keyword.decode("ascii"): item.val.decode("utf-8")
        for item in db.pgconn.info
        if item.keyword in wanted and item.val is not None
    }
    need(
        params.get("sslmode") == "verify-full"
        and params.get("channel_binding") == "require"
        and params.get("ssl_min_protocol_version") == "TLSv1.2"
        and bool(params.get("sslrootcert")),
        "CLIENT_TLS_POLICY",
    )
    if target is not None:
        need(
            db.info.host == target["host"]
            and db.info.dbname == target["database"]
            and db.info.user == target["role"],
            "SECURITY_TARGET",
        )
    row = db.execute(
        "SELECT ssl, version FROM pg_catalog.pg_stat_ssl WHERE pid=pg_backend_pid()"
    ).fetchone()
    need(
        isinstance(row, tuple)
        and len(row) == 2
        and type(row[0]) is bool
        and (row[1] is None or type(row[1]) is str),
        "BACKEND_OBSERVATION",
    )
    if security_mode == "native-postgres-tls":
        need(row in ((True, "TLSv1.2"), (True, "TLSv1.3")), "BACKEND_TLS")
    else:
        # A positively observed obsolete backend TLS version needs review.
        # ssl=false alone does not describe a provider's surrounding transport.
        need(not row[0] or row[1] in ("TLSv1.2", "TLSv1.3"), "BACKEND_TLS")
    return {
        "client_tls_protocol": protocol.decode("ascii"),
        "client_tls_policy_verified": True,
        "pg_stat_ssl": {"ssl": row[0], "version": row[1]},
        "internal_path_assurance": (
            "vendor-assertion-not-independently-verified"
            if security_mode == "neon-managed"
            else "observed-postgres-connection-tls"
        ),
    }


def load_engine():
    raw = ENGINE.read_bytes()
    need(sha(raw) == ENGINE_SHA, "ENGINE_PIN")
    spec = importlib.util.spec_from_file_location("sealed_operating_backup", ENGINE)
    engine = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(ENGINE), "exec"), engine.__dict__)  # noqa: S102 - bytes verified against ENGINE_SHA
    module, prep = engine.load_sealed()
    return engine, module, prep


BUDGET_INDEX = "CREATE UNIQUE INDEX uq_budget_current ON public.app_budget_window USING btree (is_current) WHERE is_current"


def hazard_sql(module):
    sql = module.HAZARD_SQL
    if len(module.C.TABLES) in (30, 33):
        exact = (
            "c.relname='app_budget_window' AND i.relname='uq_budget_current' AND x.indisunique AND pg_catalog.pg_get_expr(x.indpred,x.indrelid)='is_current' AND pg_catalog.pg_get_indexdef(i.oid)='"
            + BUDGET_INDEX
            + "'"
        )
        need(sql.count("x.indpred IS NOT NULL") == 1, "CATALOG_QUERY_PIN")
        sql = sql.replace(
            "x.indpred IS NOT NULL", "(x.indpred IS NOT NULL AND NOT (" + exact + "))"
        )
    return sql


def comparison(module, db, check):
    # Same reviewed catalog SQL, complete definitions and encrypted row hashes.
    for sql in module.SESSION_SETTINGS:
        check()
        db.execute(sql).close()
    need(
        module.select_rows(db, hazard_sql(module), check, 1) == [(0,) * 10],
        "CATALOG_SCOPE",
    )
    need(
        module.select_rows(db, module.EXTRA_HAZARDS, check, 1) == [(0,) * 4],
        "CATALOG_SCOPE",
    )
    extensions = module.select_rows(
        db,
        "SELECT extname,extversion FROM pg_catalog.pg_extension ORDER BY extname",
        check,
        5,
    )
    need(extensions == [("plpgsql", "1.0"), ("uuid-ossp", "1.1")], "EXTENSIONS")
    schema = {
        k: module.select_rows(db, sql, check) for k, sql in module.SCHEMA_SQL.items()
    }
    need(
        len(schema["relations"]) == len(module.C.TABLES)
        and {r[0] for r in schema["relations"]} == set(module.C.TABLES)
        and all(tuple(r[1:]) == ("r", "p", False, False) for r in schema["relations"]),
        "TABLE_INVENTORY",
    )
    if len(module.C.TABLES) in (30, 33):
        need(
            [
                r
                for r in schema["indexes"]
                if r[0:2] == ("app_budget_window", "uq_budget_current")
            ]
            == [("app_budget_window", "uq_budget_current", True, True, BUDGET_INDEX)],
            "BUDGET_INDEX_SCOPE",
        )
    module.locale_arguments(schema["database_locale"])
    need(
        all(
            r[0] in module.C.TABLES
            and r[2] in ("c", "f", "p", "u", "n")
            and r[3] is True
            for r in schema["constraints"]
        ),
        "CONSTRAINT_SCOPE",
    )
    need(
        all(r[0] in module.C.TABLES and r[5] == r[6] == "" for r in schema["columns"]),
        "COLUMN_SCOPE",
    )
    rows = {}
    for name in module.C.TABLES:
        need(re.fullmatch("[a-z_]+", name) is not None, "TABLE_NAME")
        sql = (
            "SELECT pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(pg_catalog.row_to_json(t)::text,'UTF8')),'hex') FROM public.\""
            + name
            + '" AS t ORDER BY 1 LIMIT 50001'
        )
        rows[name] = module.select_rows(db, sql, check, 50000)
        need(
            sum(map(len, rows.values())) <= 100000
            and all(
                len(r) == 1 and re.fullmatch("[0-9a-f]{64}", r[0]) for r in rows[name]
            ),
            "ROW_LIMIT",
        )
    result = json.loads(
        json.dumps({"schema": schema, "rows": rows, "extensions": extensions})
    )
    need(len(json.dumps(result).encode()) <= 4 * 1024 * 1024, "MANIFEST_LIMIT")
    return result


def validate_grant(grant, profile, at):
    need(
        grant.get("authorized") is True
        and grant.get("operation") == "single-production-operating-backup",
        "NOT_AUTHORIZED",
    )
    need(re.fullmatch("[a-f0-9]{12}", grant.get("run_id", "")) is not None, "RUN_ID")
    start, end = (datetime.fromisoformat(grant[k]) for k in ("starts_at", "expires_at"))
    need(
        start.tzinfo
        and end.tzinfo
        and start <= at < end <= start + timedelta(minutes=30),
        "WINDOW",
    )
    need(
        grant.get("profile_sha256")
        == sha(json.dumps(profile, sort_keys=True).encode()),
        "PROFILE_PIN",
    )
    need(grant.get("tool_sha256") == sha(Path(__file__).read_bytes()), "TOOL_PIN")
    security_policy(grant, profile, at)
    need(profile["mode"] in PROFILE_HEADS, "PROFILE")
    base, head, tables = PROFILE_HEADS[profile["mode"]]
    need(
        profile["migration_head"] == head
        and profile["table_count"] == tables
        and profile["accepted_base"] == base,
        "PROFILE",
    )
    source = Path(profile["source_root"])
    need(source.is_dir() and not source.is_symlink(), "SOURCE_PIN")
    actual = {
        str(p.relative_to(source)): sha(p.read_bytes())
        for p in sorted((source / "backend/app").rglob("*.py"))
    }
    need(actual == profile["source_files"], "SOURCE_PIN")
    if grant.get("sequence", 0):
        due_time(
            datetime.fromisoformat(grant["opening_snapshot_at"]), grant["sequence"], at
        )
    return end


def strict_connector(base):
    class StrictConnector(base):
        def __init__(self, native, check, resolver=None):
            def strict_native(**params):
                return native(**(params | {"ssl_min_protocol_version": "TLSv1.2"}))

            super().__init__(strict_native, check, resolver)

    return StrictConnector


def capacity_admission(grant, profile, at):
    """New grants bind the helper and reviewed bounds before engine/input I/O."""
    need(
        type(grant.get("capacity_schema")) is int and grant["capacity_schema"] == 1,
        "CAPACITY_VERSION",
    )
    path = Path(__file__).with_name("backup_capacity.py")
    need(
        path.is_file() and not path.is_symlink() and path.stat().st_size <= 262144,
        "CAPACITY_HELPER",
    )
    need(
        sha(path.read_bytes()) == grant.get("capacity_helper_sha256"),
        "CAPACITY_HELPER_PIN",
    )
    spec = importlib.util.spec_from_file_location("_backup_capacity", path)
    capacity = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(capacity)
    # The current authorization retains the original backend-TLS requirement.
    # Existing mode readers remain available; this new executable path cannot
    # substitute managed evidence for the required backend TLS observation.
    need(profile.get("security_mode") == "native-postgres-tls", "BACKEND_TLS")
    policy, evidence = grant.get("capacity_policy"), grant.get("capacity_evidence")
    capacity.validate(
        policy,
        evidence,
        at=at,
        target_sha256=sha(json.dumps(profile["target"], sort_keys=True).encode()),
        profile_sha256=grant["profile_sha256"],
        host_sha256=capacity.host_identity(),
    )
    need(type(grant.get("initialize_capacity_ledger")) is bool, "CAPACITY_INITIALIZE")
    return capacity, policy, evidence


def execute(grant, profile):
    capacity, policy, evidence = capacity_admission(grant, profile, datetime.now(UTC))
    engine, module, prep = load_engine()
    end = validate_grant(grant, profile, datetime.now(UTC))
    need(
        sys.flags.isolated
        and sys.dont_write_bytecode
        and all(f.isatty() for f in (sys.stdin, sys.stdout, sys.stderr)),
        "OWNER_TERMINAL",
    )
    root = (
        Path.home() / "Documents/vireal-backups/production-operating" / grant["run_id"]
    )
    need(not root.exists(), "ATTEMPT_CONSUMED")
    ledger = capacity.Ledger(
        Path.home() / "Documents/vireal-backups/production-operating-capacity", policy
    )
    # This is deliberately shared across run IDs, profiles and opening runs.
    # Initialization is explicit and possible once; no missing-ledger recovery.
    capacity_admission(grant, profile, datetime.now(UTC))
    reservation = ledger.reserve(
        grant["run_id"],
        grant.get("capture_id"),
        grant.get("capacity_stream"),
        grant.get("capture_kind"),
        at=datetime.now(UTC),
        initialize=grant["initialize_capacity_ledger"],
    )
    try:
        return execute_reserved(
            grant,
            profile,
            engine,
            module,
            prep,
            end,
            root,
            capacity,
            policy,
            evidence,
            ledger,
            reservation,
        )
    except BaseException:
        try:
            ledger.finish(grant["run_id"])
        except (ValueError, OSError):
            # The durable reservation remains charged even if recording the
            # unknown result fails. Never repair, retry or free it here.
            pass
        raise


def capacity_receipt(capacity, policy, grant, report, at):
    need(
        report.get("icloud_uploaded") is True
        and report.get("cadence_passed") is True
        and report.get("capture_run_id") == grant["run_id"]
        and report.get("capacity_policy_sha256") == capacity.digest(policy)
        and report.get("profile_sha256") == grant["profile_sha256"]
        and report.get("tool_sha256") == grant["tool_sha256"]
        and report.get("target") == grant["target"],
        "CAPACITY_RECEIPT",
    )
    capacity.count(report.get("ciphertext_bytes"), 1, policy["cipher_bytes"])
    capacity.sha(report.get("ciphertext_sha256"))
    capacity.sha(report.get("manifest_sha256"))
    snapshot = capacity.instant(report.get("snapshot_at"))
    uploaded = capacity.instant(report.get("icloud_uploaded_observed_at"))
    latest = capacity.instant(report.get("latest_upload_confirmation_at"))
    need(
        capacity.instant(policy["starts_at"]) <= snapshot <= uploaded <= at
        and uploaded <= latest <= snapshot + timedelta(minutes=15)
        and uploaded < capacity.instant(policy["ends_at"])
        and at < capacity.instant(grant["expires_at"]),
        "CAPACITY_RECEIPT_TIME",
    )
    need(
        capacity.instant(report.get("retain_at_least_until"))
        >= snapshot + timedelta(days=14),
        "CAPACITY_RETENTION",
    )


def execute_reserved(
    grant,
    profile,
    engine,
    module,
    prep,
    end,
    root,
    capacity,
    policy,
    evidence,
    ledger,
    reservation,
):
    module.private_dir(root.parent.parent)
    root.parent.mkdir(mode=0o700, exist_ok=True)
    module.private_dir(root.parent)
    root.mkdir(mode=0o700)
    module.private_dir(root)
    engine.ROOT = module.C.ROOT = root
    engine.load_sealed = lambda: (module, prep)
    old_safe_stop = engine.safe_stop
    categories = {
        "CLIENT_TLS_DRIVER",
        "BACKEND_TLS",
        "CLIENT_TLS",
        "CLIENT_TLS_PROTOCOL",
        "CLIENT_TLS_POLICY",
        "BACKEND_OBSERVATION",
        "SECURITY_MODE",
        "SECURITY_TARGET",
        "SECURITY_EVIDENCE",
        "SECURITY_EVIDENCE_PIN",
        "SECURITY_EVIDENCE_SCOPE",
        "SECURITY_REVIEW_WINDOW",
        "SECURITY_SOURCES",
        "SECURITY_SOURCE_PIN",
        "BUDGET_INDEX_SCOPE",
        "CATALOG_SCOPE",
        "SOURCE_PIN",
        "WINDOW",
        "SLOT_WINDOW",
    }

    def safe_stop(error, owner_module=None):
        code = error.args[0] if error.args else None
        return (
            code
            if isinstance(code, str) and code in categories
            else old_safe_stop(error, owner_module)
        )

    engine.safe_stop = safe_stop
    module.C.HEAD = profile["migration_head"]
    additions = profile_extra_tables(profile["mode"])
    module.C.TABLES = tuple(sorted((*module.C.TABLES, *additions)))
    need(
        len(module.C.TABLES) == profile["table_count"]
        and len(set(module.C.TABLES)) == len(module.C.TABLES),
        "TABLE_INVENTORY",
    )
    module.private_comparison = lambda db, check: comparison(module, db, check)
    original = engine.operating_snapshot
    observation = {}

    def snapshot(m, db, check, email):
        engine.ACTIVE_IO.event("SOURCE_CONNECTION_SECURITY_CHECK")
        need(datetime.now(UTC) < end, "WINDOW")
        validate_grant(grant, profile, datetime.now(UTC))
        capacity_admission(grant, profile, datetime.now(UTC))
        observation.update(
            backend_tls(
                db, security_mode=profile["security_mode"], target=profile["target"]
            )
        )
        return original(m, db, check, email)

    engine.operating_snapshot = snapshot
    module.R.Connector = strict_connector(module.R.Connector)
    connector = module.R.Connector

    class CapacityConnector(connector):
        def __call__(self, *args, **kwargs):
            capacity_admission(grant, profile, datetime.now(UTC))
            return super().__call__(*args, **kwargs)

    module.R.Connector = CapacityConnector
    source_env = module.C.source_env

    def checked_source_env(params, address):
        capacity_admission(grant, profile, datetime.now(UTC))
        return {**source_env(params, address), "PGSSLMINPROTOCOLVERSION": "TLSv1.2"}

    module.C.source_env = checked_source_env
    seal = module.C.seal_archive

    def bounded_seal(*args, **kwargs):
        value = seal(*args, **kwargs)
        capacity.check_cipher(value, policy)
        return value

    module.C.seal_archive = bounded_seal

    def slot_time(m, _slot):
        if grant.get("sequence", 0):
            return due_time(
                datetime.fromisoformat(grant["opening_snapshot_at"]),
                grant["sequence"],
                datetime.now(UTC),
            )
        return None

    engine.slot_time = slot_time
    # Both artifact and receipt names remain unique within the new run directory.
    # Previous completed receipt is copied as non-secret evidence, never a DB row.
    if grant.get("sequence", 0):
        previous_path = Path(grant["previous_receipt"])
        raw_prior = module.read_safe(previous_path)
        need(sha(raw_prior) == grant["previous_receipt_sha256"], "PREVIOUS_RECEIPT_PIN")
        prior = json.loads(raw_prior)
        need(
            prior["profile_sha256"] == grant["profile_sha256"]
            and prior["sequence"] == grant["sequence"] - 1
            and prior["security_mode"] == grant["security_mode"]
            and prior["target"] == grant["target"]
            and prior["tool_sha256"] == grant["tool_sha256"],
            "PREVIOUS_PROFILE",
        )
        need(prior["icloud_uploaded"] and prior["cadence_passed"], "PREVIOUS_RECEIPT")
        previous_at = datetime.fromisoformat(prior["snapshot_at"])
        expected_previous = datetime.fromisoformat(
            grant["opening_snapshot_at"]
        ) + timedelta(minutes=45 * (grant["sequence"] - 1))
        need(
            expected_previous <= previous_at < expected_previous + timedelta(minutes=2),
            "PREVIOUS_SNAPSHOT",
        )
        module.write_new(root / "slot-0.json", engine.encoded(prior))
    encode = engine.encoded

    def encoded(value):
        if isinstance(value, dict) and "cadence_passed" in value:
            need(
                observation.get("client_tls_policy_verified") is True,
                "CLIENT_TLS_POLICY",
            )
            value = value | {
                "profile_sha256": grant["profile_sha256"],
                "sequence": grant.get("sequence", 0),
                "capture_run_id": grant["run_id"],
                "tool_sha256": grant["tool_sha256"],
                "security_mode": grant["security_mode"],
                "vendor_evidence_sha256": grant["vendor_evidence_sha256"],
                "target": grant["target"],
                "capacity_policy_sha256": reservation["policy_sha256"],
                **observation,
            }
        result = encode(value)
        if isinstance(value, dict) and set(value) == {
            "archive",
            "ciphertext_bytes",
            "ciphertext_sha256",
            "snapshot_at",
            "retain_at_least_until",
        }:
            capacity.check_sidecar(result, policy)
        return result

    engine.encoded = encoded
    # Native's immutable process deadline is the earlier of 16 min and grant end.
    old_native = engine.native
    engine.native = lambda m, p, deadline, tag: old_native(
        m, p, min(deadline, end), tag
    )
    slot = "1" if grant.get("sequence", 0) else "0"
    result = engine.run_cli(["--backup", slot])
    if result != 0:
        ledger.finish(grant["run_id"])
        return result
    capacity_admission(grant, profile, datetime.now(UTC))
    raw = module.read_safe(root / f"slot-{slot}.json")
    report = unique_json(raw)
    capacity_receipt(capacity, policy, grant, report, datetime.now(UTC))
    ledger.finish(
        grant["run_id"],
        outcome="confirmed",
        snapshot_at=report["snapshot_at"],
        retain_until=report["retain_at_least_until"],
        receipt_sha256=sha(raw),
    )
    return result


if __name__ == "__main__":
    try:
        need(len(sys.argv) == 4 and sys.argv[1] == "--execute", "NOT_AUTHORIZED")
        raise SystemExit(
            execute(
                unique_json(Path(sys.argv[2]).read_bytes()),
                unique_json(Path(sys.argv[3]).read_bytes()),
            )
        )
    except (Exception, KeyboardInterrupt):  # noqa: BLE001 - unknown outcome always stops without retry
        print("营业备份已停止 (SAFE_STOP_NO_RETRY)。", flush=True)
        raise SystemExit(2) from None
