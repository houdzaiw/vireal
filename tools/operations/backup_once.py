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


def backend_tls(db):
    need(db.pgconn.ssl_in_use, "CLIENT_TLS")
    need(
        negotiated_tls_protocol(db.pgconn) in (b"TLSv1.2", b"TLSv1.3"),
        "CLIENT_TLS_PROTOCOL",
    )
    need(
        db.execute(
            "SELECT ssl, version FROM pg_catalog.pg_stat_ssl WHERE pid=pg_backend_pid()"
        ).fetchone()
        in ((True, "TLSv1.2"), (True, "TLSv1.3")),
        "BACKEND_TLS",
    )


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


def execute(grant, profile):
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

    def snapshot(m, db, check, email):
        engine.ACTIVE_IO.event("SOURCE_AND_BACKEND_TLS_CHECK")
        need(datetime.now(UTC) < end, "WINDOW")
        validate_grant(grant, profile, datetime.now(UTC))
        backend_tls(db)
        return original(m, db, check, email)

    engine.operating_snapshot = snapshot
    module.R.Connector = strict_connector(module.R.Connector)
    source_env = module.C.source_env
    module.C.source_env = lambda params, address: {
        **source_env(params, address),
        "PGSSLMINPROTOCOLVERSION": "TLSv1.2",
    }

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
            and prior["sequence"] == grant["sequence"] - 1,
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
            value = value | {
                "profile_sha256": grant["profile_sha256"],
                "sequence": grant.get("sequence", 0),
            }
        return encode(value)

    engine.encoded = encoded
    # Native's immutable process deadline is the earlier of 16 min and grant end.
    old_native = engine.native
    engine.native = lambda m, p, deadline, tag: old_native(
        m, p, min(deadline, end), tag
    )
    return engine.run_cli(["--backup", "1" if grant.get("sequence", 0) else "0"])


if __name__ == "__main__":
    try:
        need(len(sys.argv) == 4 and sys.argv[1] == "--execute", "NOT_AUTHORIZED")
        raise SystemExit(
            execute(
                json.loads(Path(sys.argv[2]).read_text()),
                json.loads(Path(sys.argv[3]).read_text()),
            )
        )
    except (Exception, KeyboardInterrupt):  # noqa: BLE001 - unknown outcome always stops without retry
        print("营业备份已停止 (SAFE_STOP_NO_RETRY)。", flush=True)
        raise SystemExit(2) from None
