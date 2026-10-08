import pytest

from app.services.effect_validation import (
    execution_type_for_model,
    validate_effect_variant,
)
from app.services.replicate_video import (
    MINIMAX_VIDEO_01_MODEL,
    SEEDANCE_R2V_MODEL,
    WAN_R2V_MODEL,
)


@pytest.mark.parametrize(
    ("model", "image_count", "duration", "negative_prompt"),
    [
        (MINIMAX_VIDEO_01_MODEL, 1, 5, "watermark"),
        (WAN_R2V_MODEL, 1, 2, "watermark"),
        (WAN_R2V_MODEL, 5, 10, None),
        (SEEDANCE_R2V_MODEL, 1, 2, None),
        (SEEDANCE_R2V_MODEL, 9, 15, None),
    ],
)
def test_validate_effect_variant_accepts_supported_boundaries(
    model: str,
    image_count: int,
    duration: int,
    negative_prompt: str | None,
) -> None:
    validate_effect_variant(
        provider="replicate",
        model=model,
        input_image_count=image_count,
        duration_seconds=duration,
        prompt=" cinematic motion ",
        negative_prompt=negative_prompt,
    )


@pytest.mark.parametrize(
    ("provider", "model", "image_count", "duration", "prompt", "negative_prompt"),
    [
        ("local", MINIMAX_VIDEO_01_MODEL, 1, 5, "motion", None),
        ("replicate", "unknown/model", 1, 5, "motion", None),
        ("replicate", MINIMAX_VIDEO_01_MODEL, 1, 5, "  ", None),
        ("replicate", MINIMAX_VIDEO_01_MODEL, 2, 5, "motion", None),
        ("replicate", MINIMAX_VIDEO_01_MODEL, 1, 10, "motion", None),
        ("replicate", WAN_R2V_MODEL, 0, 5, "motion", None),
        ("replicate", WAN_R2V_MODEL, 1, 11, "motion", None),
        ("replicate", SEEDANCE_R2V_MODEL, 0, 5, "motion", None),
        ("replicate", SEEDANCE_R2V_MODEL, 1, 16, "motion", None),
        ("replicate", SEEDANCE_R2V_MODEL, 2, 15, "motion", "watermark"),
    ],
)
def test_validate_effect_variant_rejects_invalid_configuration(
    provider: str,
    model: str,
    image_count: int,
    duration: int,
    prompt: str,
    negative_prompt: str | None,
) -> None:
    with pytest.raises(ValueError):
        validate_effect_variant(
            provider=provider,
            model=model,
            input_image_count=image_count,
            duration_seconds=duration,
            prompt=prompt,
            negative_prompt=negative_prompt,
        )


def test_execution_type_for_model_maps_whitelist() -> None:
    assert execution_type_for_model(MINIMAX_VIDEO_01_MODEL) == "minimax"
    assert execution_type_for_model(WAN_R2V_MODEL) == "wan"
    assert execution_type_for_model(SEEDANCE_R2V_MODEL) == "seedance"
    with pytest.raises(ValueError, match="Unsupported effect model"):
        execution_type_for_model("unknown/model")
