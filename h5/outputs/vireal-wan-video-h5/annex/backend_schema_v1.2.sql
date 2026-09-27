-- Vireal v1.2 catalogue schema draft for PostgreSQL.
-- Convert this draft into an Alembic migration before execution.

BEGIN;

CREATE TABLE app_managed_media_asset (
    id UUID PRIMARY KEY,
    kind VARCHAR(30) NOT NULL CHECK (kind IN ('poster', 'preview_video')),
    object_key VARCHAR(2048) NOT NULL UNIQUE,
    content_type VARCHAR(100) NOT NULL,
    size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
    checksum_sha256 VARCHAR(64) NOT NULL,
    width INTEGER,
    height INTEGER,
    duration_ms INTEGER,
    status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('uploading', 'active', 'failed', 'deleted')),
    uploaded_by UUID REFERENCES "user"(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ,
    CHECK (width IS NULL OR width > 0),
    CHECK (height IS NULL OR height > 0),
    CHECK (duration_ms IS NULL OR duration_ms >= 0)
);

CREATE INDEX ix_app_managed_media_asset_kind_status
    ON app_managed_media_asset(kind, status);

CREATE TABLE app_effect_category (
    id UUID PRIMARY KEY,
    slug VARCHAR(80) NOT NULL UNIQUE,
    name_zh VARCHAR(120) NOT NULL,
    name_en VARCHAR(120) NOT NULL,
    tones_json TEXT NOT NULL DEFAULT '["#476b70","#18262c","#98d9de"]',
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_by UUID REFERENCES "user"(id) ON DELETE SET NULL,
    updated_by UUID REFERENCES "user"(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_app_effect_category_public_order
    ON app_effect_category(is_enabled, sort_order, created_at);

CREATE TABLE app_effect (
    id UUID PRIMARY KEY,
    category_id UUID NOT NULL REFERENCES app_effect_category(id) ON DELETE RESTRICT,
    slug VARCHAR(120) NOT NULL UNIQUE,
    title_zh VARCHAR(160) NOT NULL,
    title_en VARCHAR(160) NOT NULL,
    description TEXT,
    input_image_count SMALLINT NOT NULL DEFAULT 1 CHECK (input_image_count IN (1, 2)),
    poster_asset_id UUID REFERENCES app_managed_media_asset(id) ON DELETE SET NULL,
    preview_asset_id UUID REFERENCES app_managed_media_asset(id) ON DELETE SET NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    publish_status VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (publish_status IN ('draft', 'published', 'archived')),
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    published_at TIMESTAMPTZ,
    created_by UUID REFERENCES "user"(id) ON DELETE SET NULL,
    updated_by UUID REFERENCES "user"(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_app_effect_category_order
    ON app_effect(category_id, is_enabled, sort_order, created_at);
CREATE INDEX ix_app_effect_publish_status
    ON app_effect(publish_status, is_enabled);

CREATE TABLE app_effect_variant (
    id UUID PRIMARY KEY,
    effect_id UUID NOT NULL REFERENCES app_effect(id) ON DELETE CASCADE,
    duration_seconds INTEGER NOT NULL CHECK (duration_seconds BETWEEN 1 AND 60),
    coin_cost INTEGER NOT NULL CHECK (coin_cost >= 0),
    provider VARCHAR(30) NOT NULL,
    model VARCHAR(255) NOT NULL,
    model_type VARCHAR(80) NOT NULL,
    prompt TEXT NOT NULL,
    negative_prompt TEXT,
    prompt_version VARCHAR(40) NOT NULL DEFAULT 'v1',
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_app_effect_variant_duration UNIQUE (effect_id, duration_seconds)
);

CREATE INDEX ix_app_effect_variant_active
    ON app_effect_variant(effect_id, is_enabled, duration_seconds);

CREATE TABLE app_effect_recommendation (
    effect_id UUID NOT NULL REFERENCES app_effect(id) ON DELETE CASCADE,
    recommended_effect_id UUID NOT NULL REFERENCES app_effect(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (effect_id, recommended_effect_id),
    CHECK (effect_id <> recommended_effect_id)
);

CREATE INDEX ix_app_effect_recommendation_order
    ON app_effect_recommendation(effect_id, sort_order);

ALTER TABLE app_video_task
    ADD COLUMN IF NOT EXISTS effect_id UUID REFERENCES app_effect(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS variant_id UUID REFERENCES app_effect_variant(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS coin_cost_snapshot INTEGER,
    ADD COLUMN IF NOT EXISTS prompt_version_snapshot VARCHAR(40);

CREATE INDEX IF NOT EXISTS ix_app_video_task_effect_id ON app_video_task(effect_id);
CREATE INDEX IF NOT EXISTS ix_app_video_task_variant_id ON app_video_task(variant_id);

-- Reversible feature switch. Public H5 and task validation read this key.
INSERT INTO app_config (id, key, value, description, is_enabled, created_at, updated_at)
VALUES (
    uuid_generate_v4(),
    'adult_authorization_required',
    'false',
    'Temporarily disabled for Vireal v1.2; retained for reversible rollout',
    TRUE,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
)
ON CONFLICT (key) DO UPDATE
SET value = EXCLUDED.value,
    description = EXCLUDED.description,
    is_enabled = EXCLUDED.is_enabled,
    updated_at = CURRENT_TIMESTAMP;

COMMIT;
