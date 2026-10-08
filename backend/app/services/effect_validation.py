from app.services.replicate_video import (
    MINIMAX_VIDEO_01_MODEL,
    SEEDANCE_R2V_MODEL,
    WAN_R2V_MODEL,
)

SUPPORTED_EFFECT_MODELS = frozenset(
    {MINIMAX_VIDEO_01_MODEL, WAN_R2V_MODEL, SEEDANCE_R2V_MODEL}
)


def validate_effect_variant(
    *,
    provider: str,
    model: str,
    input_image_count: int,
    duration_seconds: int,
    prompt: str,
    negative_prompt: str | None,
) -> None:
    if provider != "replicate":
        raise ValueError("Only the Replicate provider is enabled for v1.2")
    if model not in SUPPORTED_EFFECT_MODELS:
        raise ValueError("Model is not in the production effect whitelist")
    if not prompt.strip():
        raise ValueError("Prompt is required")
    if model == MINIMAX_VIDEO_01_MODEL:
        if input_image_count != 1 or duration_seconds != 5:
            raise ValueError("MiniMax requires one image and a five-second duration")
    elif model == WAN_R2V_MODEL:
        if not 1 <= input_image_count <= 5 or not 2 <= duration_seconds <= 10:
            raise ValueError("Wan requires 1–5 images and a 2–10 second duration")
    elif model == SEEDANCE_R2V_MODEL:
        if not 1 <= input_image_count <= 9 or not 2 <= duration_seconds <= 15:
            raise ValueError("Seedance requires 1–9 images and a 2–15 second duration")
        if negative_prompt:
            raise ValueError("Seedance does not accept a negative prompt")


def execution_type_for_model(model: str) -> str:
    if model == MINIMAX_VIDEO_01_MODEL:
        return "minimax"
    if model == WAN_R2V_MODEL:
        return "wan"
    if model == SEEDANCE_R2V_MODEL:
        return "seedance"
    raise ValueError("Unsupported effect model")
