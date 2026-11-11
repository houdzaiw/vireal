"""Pure repair plan for an isolated candidate-33 restore, never a live executor.

Recreate four fixed migration CHECKs, then require raw full-manifest equality.
No generic SQL normalization, acceptance exception, connection, or grant bypass.
The caller must first authenticate the archive and validate the complete catalog.
"""

TABLES = frozenset(
    "alembic_version app_admin_operation_log app_coin_account app_coin_ledger "
    "app_config app_content app_content_image app_device app_effect "
    "app_effect_category app_effect_recommendation app_effect_variant "
    "app_generation app_managed_media_asset app_order app_order_event "
    "app_payment_case app_paypal_replacement app_upload app_user "
    "app_user_identity app_user_session app_video_task app_video_task_webhook_event "
    "item user app_budget_window app_cost_observation app_cost_reservation "
    "app_operational_alert app_resource_policy app_resource_attempt "
    "app_media_read_grant".split()
)

# Fixed public declarations from the reviewed migration chain.
SPECS = (
    (
        "app_budget_window",
        "app_budget_window_state_check",
        {"state": "character varying"},
        "state IN ('draft', 'active', 'paused', 'closed')",
        "CHECK (state::text = ANY (ARRAY['draft'::character varying, 'active'::character varying, 'paused'::character varying, 'closed'::character varying]::text[]))",
    ),
    (
        "app_effect",
        "app_effect_publish_status_check",
        {"publish_status": "character varying(20)"},
        "publish_status IN ('draft', 'published', 'archived')",
        "CHECK (publish_status::text = ANY (ARRAY['draft'::character varying, 'published'::character varying, 'archived'::character varying]::text[]))",
    ),
    (
        "app_managed_media_asset",
        "app_managed_media_asset_kind_check",
        {"kind": "character varying(30)"},
        "kind IN ('poster', 'preview_video')",
        "CHECK (kind::text = ANY (ARRAY['poster'::character varying, 'preview_video'::character varying]::text[]))",
    ),
    (
        "app_order",
        "ck_app_order_paypal_snapshot",
        {
            "provider": "character varying(20)",
            "amount": "integer",
            "currency": "character varying(3)",
            "coin_quantity": "integer",
            "payment_environment": "character varying(10)",
            "payment_idempotency_key": "character varying(120)",
        },
        "provider <> 'paypal' OR (amount IS NOT NULL AND amount > 0 AND currency IS NOT NULL AND currency = 'USD' AND coin_quantity IS NOT NULL AND coin_quantity > 0 AND payment_environment IS NOT NULL AND payment_environment IN ('sandbox','live') AND payment_idempotency_key IS NOT NULL)",
        "CHECK (provider::text <> 'paypal'::text OR amount IS NOT NULL AND amount > 0 AND currency IS NOT NULL AND currency::text = 'USD'::text AND coin_quantity IS NOT NULL AND coin_quantity > 0 AND payment_environment IS NOT NULL AND (payment_environment::text = ANY (ARRAY['sandbox'::character varying, 'live'::character varying]::text[])) AND payment_idempotency_key IS NOT NULL)",
    ),
)


def restored_definition(original: str) -> str:
    # Derive exactly the known pg_dump rendering of one fixed ARRAY segment.
    start = original.index("ARRAY[")
    end = original.index("]::text[]", start)
    array = original[start:end].replace(
        "::character varying", "::character varying::text"
    )
    return original[:start] + array + "]" + original[end + len("]::text[]") :]


def require(value: bool) -> None:
    if not value:
        raise ValueError("CANDIDATE_RESTORE_SCOPE")


def repair_plan(
    source: dict, restored: dict, *, profile: str, head: str
) -> tuple[str, ...]:
    """Return fixed statements only; apply atomically in an isolated restore copy.

    No acceptance is returned: after applying, the caller must recapture the
    entire raw manifest and demand source == restored before any qualification.
    """
    try:
        require(profile == "candidate-33" and head == "e7f8a9b0c1d2")
        require(set(source) == set(restored) == {"schema", "rows", "extensions"})
        require(set(source["rows"]) == set(restored["rows"]) == TABLES)
        require(source["rows"] == restored["rows"])
        require(source["extensions"] == restored["extensions"])
        a, b = source["schema"], restored["schema"]
        require(
            set(a)
            == set(b)
            == {
                "database_locale",
                "relations",
                "columns",
                "constraints",
                "indexes",
                "collations",
            }
        )
        require(all(a[k] == b[k] for k in a if k != "constraints"))
        require(len(a["relations"]) == 33 and {r[0] for r in a["relations"]} == TABLES)
        require(all(r[1:] == ["r", "p", False, False] for r in a["relations"]))
        maps = []
        for schema in (a, b):
            rows = schema["constraints"]
            require(
                all(
                    type(row) is list and len(row) == 5 and type(row[3]) is bool
                    for row in rows
                )
            )
            mapping = {(r[0], r[1]): r for r in rows}
            require(len(mapping) == len(rows))
            maps.append(mapping)
        require(maps[0].keys() == maps[1].keys())
        require(
            {k for k in maps[0] if maps[0][k] != maps[1][k]}
            == {(s[0], s[1]) for s in SPECS}
        )
        plan = []
        for table, name, types, expression, definition in SPECS:
            require(maps[0][table, name] == [table, name, "c", True, definition])
            require(
                maps[1][table, name]
                == [table, name, "c", True, restored_definition(definition)]
            )
            for schema in (a, b):
                columns = [
                    r for r in schema["columns"] if r[0] == table and r[2] in types
                ]
                require(
                    len(columns) == len(types)
                    and {r[2]: r[3] for r in columns} == types
                )
            # Every byte comes from SPECS; never interpolate manifest SQL.
            plan.extend(
                (
                    f'ALTER TABLE public."{table}" DROP CONSTRAINT "{name}"',
                    f'ALTER TABLE public."{table}" ADD CONSTRAINT "{name}" CHECK ({expression})',
                )
            )
        return tuple(plan)
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ValueError("CANDIDATE_RESTORE_SCOPE") from exc
