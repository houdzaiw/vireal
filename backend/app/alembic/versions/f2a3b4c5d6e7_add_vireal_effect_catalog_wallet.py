"""Add the Vireal v1.2 effect catalogue and coin wallet.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-09-27 12:00:00.000000
"""

import json
import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op


revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None

NAMESPACE = uuid.UUID("52d1f00e-91fb-4cc0-aefb-5a8d3b6fb7a4")


def stable_id(value: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, value)


def upgrade() -> None:
    op.create_table(
        "app_managed_media_asset",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(length=30), nullable=False),
        sa.Column(
            "object_key",
            sqlmodel.sql.sqltypes.AutoString(length=2048),
            nullable=False,
        ),
        sa.Column(
            "content_type",
            sqlmodel.sql.sqltypes.AutoString(length=100),
            nullable=False,
        ),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "checksum_sha256",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column(
            "status", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False
        ),
        sa.Column("uploaded_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('poster', 'preview_video')"),
        sa.CheckConstraint("size_bytes >= 0"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index(
        op.f("ix_app_managed_media_asset_kind"),
        "app_managed_media_asset",
        ["kind"],
    )
    op.create_index(
        op.f("ix_app_managed_media_asset_status"),
        "app_managed_media_asset",
        ["status"],
    )

    op.create_table(
        "app_effect_category",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sqlmodel.sql.sqltypes.AutoString(length=80), nullable=False),
        sa.Column(
            "name_zh", sqlmodel.sql.sqltypes.AutoString(length=120), nullable=False
        ),
        sa.Column(
            "name_en", sqlmodel.sql.sqltypes.AutoString(length=120), nullable=False
        ),
        sa.Column("tones_json", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_app_effect_category_slug"),
        "app_effect_category",
        ["slug"],
        unique=True,
    )
    op.create_index(
        op.f("ix_app_effect_category_sort_order"), "app_effect_category", ["sort_order"]
    )
    op.create_index(
        op.f("ix_app_effect_category_is_enabled"), "app_effect_category", ["is_enabled"]
    )

    op.create_table(
        "app_effect",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sqlmodel.sql.sqltypes.AutoString(length=120), nullable=False),
        sa.Column(
            "title_zh", sqlmodel.sql.sqltypes.AutoString(length=160), nullable=False
        ),
        sa.Column(
            "title_en", sqlmodel.sql.sqltypes.AutoString(length=160), nullable=False
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("input_image_count", sa.SmallInteger(), nullable=False),
        sa.Column("poster_asset_id", sa.Uuid(), nullable=True),
        sa.Column("preview_asset_id", sa.Uuid(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column(
            "publish_status",
            sqlmodel.sql.sqltypes.AutoString(length=20),
            nullable=False,
        ),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "recommendation_label",
            sqlmodel.sql.sqltypes.AutoString(length=80),
            nullable=True,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("input_image_count IN (1, 2)"),
        sa.CheckConstraint("publish_status IN ('draft', 'published', 'archived')"),
        sa.ForeignKeyConstraint(
            ["category_id"], ["app_effect_category.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["poster_asset_id"], ["app_managed_media_asset.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["preview_asset_id"], ["app_managed_media_asset.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("category_id", "sort_order", "publish_status", "is_enabled"):
        op.create_index(op.f(f"ix_app_effect_{column}"), "app_effect", [column])
    op.create_index(op.f("ix_app_effect_slug"), "app_effect", ["slug"], unique=True)

    op.create_table(
        "app_effect_variant",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("effect_id", sa.Uuid(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("coin_cost", sa.Integer(), nullable=False),
        sa.Column(
            "provider", sqlmodel.sql.sqltypes.AutoString(length=30), nullable=False
        ),
        sa.Column(
            "model", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False
        ),
        sa.Column(
            "model_type", sqlmodel.sql.sqltypes.AutoString(length=80), nullable=False
        ),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("negative_prompt", sa.Text(), nullable=True),
        sa.Column(
            "prompt_version",
            sqlmodel.sql.sqltypes.AutoString(length=40),
            nullable=False,
        ),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("duration_seconds BETWEEN 1 AND 60"),
        sa.CheckConstraint("coin_cost >= 0"),
        sa.ForeignKeyConstraint(["effect_id"], ["app_effect.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "effect_id", "duration_seconds", name="uq_app_effect_variant_duration"
        ),
    )
    op.create_index(
        op.f("ix_app_effect_variant_effect_id"), "app_effect_variant", ["effect_id"]
    )

    op.create_table(
        "app_effect_recommendation",
        sa.Column("effect_id", sa.Uuid(), nullable=False),
        sa.Column("recommended_effect_id", sa.Uuid(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("effect_id <> recommended_effect_id"),
        sa.ForeignKeyConstraint(["effect_id"], ["app_effect.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["recommended_effect_id"], ["app_effect.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("effect_id", "recommended_effect_id"),
    )

    op.create_table(
        "app_coin_account",
        sa.Column("app_user_id", sa.Uuid(), nullable=False),
        sa.Column("balance", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("balance >= 0"),
        sa.ForeignKeyConstraint(["app_user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("app_user_id"),
    )

    op.create_table(
        "app_coin_ledger",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("app_user_id", sa.Uuid(), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column(
            "entry_type", sqlmodel.sql.sqltypes.AutoString(length=40), nullable=False
        ),
        sa.Column(
            "idempotency_key",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("admin_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "reason", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("balance_after >= 0"),
        sa.ForeignKeyConstraint(["app_user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["task_id"], ["app_video_task.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["admin_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "app_user_id",
            "idempotency_key",
            name="uq_app_coin_ledger_user_idempotency_key",
        ),
    )
    for column in ("app_user_id", "entry_type", "task_id", "created_at"):
        op.create_index(
            op.f(f"ix_app_coin_ledger_{column}"), "app_coin_ledger", [column]
        )

    op.add_column("app_video_task", sa.Column("effect_id", sa.Uuid(), nullable=True))
    op.add_column("app_video_task", sa.Column("variant_id", sa.Uuid(), nullable=True))
    op.add_column(
        "app_video_task", sa.Column("coin_cost_snapshot", sa.Integer(), nullable=True)
    )
    op.add_column(
        "app_video_task",
        sa.Column(
            "prompt_version_snapshot",
            sqlmodel.sql.sqltypes.AutoString(length=40),
            nullable=True,
        ),
    )
    op.add_column(
        "app_video_task",
        sa.Column("coin_refunded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "app_video_task",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_app_video_task_effect",
        "app_video_task",
        "app_effect",
        ["effect_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_app_video_task_variant",
        "app_video_task",
        "app_effect_variant",
        ["variant_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_app_video_task_effect_id"), "app_video_task", ["effect_id"]
    )
    op.create_index(
        op.f("ix_app_video_task_variant_id"), "app_video_task", ["variant_id"]
    )
    op.create_index(
        op.f("ix_app_video_task_deleted_at"), "app_video_task", ["deleted_at"]
    )

    _seed_catalog()
    _seed_adult_authorization_config()


def _seed_catalog() -> None:
    now = datetime.now(UTC)
    category_table = sa.table(
        "app_effect_category",
        sa.column("id", sa.Uuid()),
        sa.column("slug", sa.String()),
        sa.column("name_zh", sa.String()),
        sa.column("name_en", sa.String()),
        sa.column("tones_json", sa.Text()),
        sa.column("sort_order", sa.Integer()),
        sa.column("is_enabled", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    effect_table = sa.table(
        "app_effect",
        sa.column("id", sa.Uuid()),
        sa.column("category_id", sa.Uuid()),
        sa.column("slug", sa.String()),
        sa.column("title_zh", sa.String()),
        sa.column("title_en", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("input_image_count", sa.Integer()),
        sa.column("sort_order", sa.Integer()),
        sa.column("publish_status", sa.String()),
        sa.column("is_enabled", sa.Boolean()),
        sa.column("recommendation_label", sa.String()),
        sa.column("published_at", sa.DateTime(timezone=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    variant_table = sa.table(
        "app_effect_variant",
        sa.column("id", sa.Uuid()),
        sa.column("effect_id", sa.Uuid()),
        sa.column("duration_seconds", sa.Integer()),
        sa.column("coin_cost", sa.Integer()),
        sa.column("provider", sa.String()),
        sa.column("model", sa.String()),
        sa.column("model_type", sa.String()),
        sa.column("prompt", sa.Text()),
        sa.column("negative_prompt", sa.Text()),
        sa.column("prompt_version", sa.String()),
        sa.column("is_default", sa.Boolean()),
        sa.column("is_enabled", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    recommendation_table = sa.table(
        "app_effect_recommendation",
        sa.column("effect_id", sa.Uuid()),
        sa.column("recommended_effect_id", sa.Uuid()),
        sa.column("sort_order", sa.Integer()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )

    categories = [
        ("kiss", "亲吻", "KISS", ["#8a4050", "#2b1728", "#d8908f"]),
        ("romance", "浪漫时刻", "ROMANCE", ["#6b536e", "#172b37", "#dcb6cf"]),
        ("charm", "迷人魅力", "CHARM", ["#5c6b81", "#182330", "#a9d5e2"]),
        ("outfit", "换装", "OUTFIT", ["#765a44", "#1d1c2b", "#e0b374"]),
        ("dance", "舞蹈", "DANCE", ["#3e6f73", "#111d38", "#a2e8d6"]),
        ("anime", "二次元", "ANIME", ["#5a4d88", "#13152e", "#b7a8ff"]),
    ]
    titles = {
        "kiss": ["心动靠近", "温柔侧吻", "电影感拥吻"],
        "romance": ["雨中相遇", "日落依偎", "烛光约会"],
        "charm": ["镜头凝望", "魅力转身", "红毯时刻"],
        "outfit": ["复古礼服", "未来机能", "晚宴造型"],
        "dance": ["节拍律动", "舞台独舞", "霓虹舞步"],
        "anime": ["次元觉醒", "魔法变身", "樱花物语"],
    }
    op.bulk_insert(
        category_table,
        [
            {
                "id": stable_id(f"category:{slug}"),
                "slug": slug,
                "name_zh": name_zh,
                "name_en": name_en,
                "tones_json": json.dumps(tones),
                "sort_order": index * 10,
                "is_enabled": True,
                "created_at": now,
                "updated_at": now,
            }
            for index, (slug, name_zh, name_en, tones) in enumerate(categories, 1)
        ],
    )

    effect_rows: list[dict[str, object]] = []
    variant_rows: list[dict[str, object]] = []
    recommendation_rows: list[dict[str, object]] = []
    for category_index, (slug, _name_zh, name_en, _tones) in enumerate(categories):
        effect_ids: list[uuid.UUID] = []
        for effect_index, title in enumerate(titles[slug], 1):
            effect_slug = f"{slug}-{effect_index}"
            effect_id = stable_id(f"effect:{effect_slug}")
            effect_ids.append(effect_id)
            prompt = (
                f"Create a cinematic {name_en.lower()} motion while preserving "
                "facial identity and natural movement."
            )
            effect_rows.append(
                {
                    "id": effect_id,
                    "category_id": stable_id(f"category:{slug}"),
                    "slug": effect_slug,
                    "title_zh": title,
                    "title_en": f"{name_en} MOTION {effect_index:02d}",
                    "description": "上传清晰的人像照片，生成专属动态短片。",
                    "input_image_count": 2 if slug in {"kiss", "romance"} else 1,
                    "sort_order": effect_index * 10,
                    "publish_status": "published",
                    "is_enabled": True,
                    "recommendation_label": "热门"
                    if effect_index == 1
                    else "推荐"
                    if effect_index == 2
                    else None,
                    "published_at": now,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            duration_specs = [
                (5, 20 + category_index * 2),
                (10, 35 + category_index * 3),
            ]
            if slug != "anime":
                duration_specs.append((15, 80 + category_index * 4))
            for duration, cost in duration_specs:
                if duration == 15:
                    model = "bytedance/seedance-2.0"
                    model_type = "seedance-video"
                elif duration == 10 or slug in {"kiss", "romance", "dance"}:
                    model = "wan-video/wan-2.7-r2v"
                    model_type = "wan-video"
                else:
                    model = "minimax/video-01"
                    model_type = "minimax-video"
                variant_rows.append(
                    {
                        "id": stable_id(f"variant:{effect_slug}:{duration}"),
                        "effect_id": effect_id,
                        "duration_seconds": duration,
                        "coin_cost": cost,
                        "provider": "replicate",
                        "model": model,
                        "model_type": model_type,
                        "prompt": prompt,
                        "negative_prompt": None,
                        "prompt_version": "v1",
                        "is_default": duration == 5,
                        "is_enabled": True,
                        "created_at": now,
                        "updated_at": now,
                    }
                )
        for index, effect_id in enumerate(effect_ids):
            for order, recommended_id in enumerate(
                [value for value in effect_ids if value != effect_id], 1
            ):
                recommendation_rows.append(
                    {
                        "effect_id": effect_id,
                        "recommended_effect_id": recommended_id,
                        "sort_order": order * 10,
                        "created_at": now,
                    }
                )
    op.bulk_insert(effect_table, effect_rows)
    op.bulk_insert(variant_table, variant_rows)
    op.bulk_insert(recommendation_table, recommendation_rows)


def _seed_adult_authorization_config() -> None:
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO app_config
                (id, key, value, description, is_enabled, created_at, updated_at)
            VALUES
                (:id, 'adult_authorization_required', 'false', :description, true, :now, :now)
            ON CONFLICT (key) DO UPDATE SET
                value = EXCLUDED.value,
                description = EXCLUDED.description,
                is_enabled = EXCLUDED.is_enabled,
                updated_at = EXCLUDED.updated_at
            """
        ),
        {
            "id": stable_id("config:adult_authorization_required"),
            "description": "Temporarily disabled for Vireal v1.2; retained for reversible rollout",
            "now": datetime.now(UTC),
        },
    )


def downgrade() -> None:
    for name in ("deleted_at", "variant_id", "effect_id"):
        op.drop_index(op.f(f"ix_app_video_task_{name}"), table_name="app_video_task")
    op.drop_constraint(
        "fk_app_video_task_variant", "app_video_task", type_="foreignkey"
    )
    op.drop_constraint("fk_app_video_task_effect", "app_video_task", type_="foreignkey")
    for column in (
        "deleted_at",
        "coin_refunded_at",
        "prompt_version_snapshot",
        "coin_cost_snapshot",
        "variant_id",
        "effect_id",
    ):
        op.drop_column("app_video_task", column)
    op.drop_table("app_coin_ledger")
    op.drop_table("app_coin_account")
    op.drop_table("app_effect_recommendation")
    op.drop_table("app_effect_variant")
    op.drop_table("app_effect")
    op.drop_table("app_effect_category")
    op.drop_table("app_managed_media_asset")
