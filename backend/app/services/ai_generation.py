import threading
import time
import uuid
from dataclasses import dataclass
from typing import Protocol

from sqlmodel import Session

from app import crud
from app.core.config import settings
from app.core.db import engine
from app.models import AppGeneration


@dataclass(frozen=True)
class AIGenerationResult:
    output_url: str | None = None
    error_message: str | None = None


class AIGenerationProvider(Protocol):
    def generate(self, generation: AppGeneration) -> AIGenerationResult:
        """Run one provider generation job and return its visible result URL."""


class LocalAIGenerationProvider:
    def generate(self, generation: AppGeneration) -> AIGenerationResult:
        time.sleep(settings.APP_GENERATION_LOCAL_DELAY_SECONDS)
        return AIGenerationResult(
            output_url=(
                generation.reference_image_url or generation.character_image_url
            ),
        )


def get_ai_generation_provider() -> AIGenerationProvider:
    return LocalAIGenerationProvider()


def run_generation(
    generation_id: uuid.UUID,
    provider: AIGenerationProvider | None = None,
) -> None:
    with Session(engine) as session:
        generation = session.get(AppGeneration, generation_id)
        if not generation or generation.deleted_at is not None:
            return

        try:
            result = (provider or get_ai_generation_provider()).generate(generation)
        except Exception as exc:  # pragma: no cover - provider-specific fallback
            crud.update_app_generation_result(
                session=session,
                generation_id=generation_id,
                status="failed",
                error_message=str(exc)[:500],
            )
            return

        if result.error_message:
            crud.update_app_generation_result(
                session=session,
                generation_id=generation_id,
                status="failed",
                error_message=result.error_message,
            )
            return

        crud.update_app_generation_result(
            session=session,
            generation_id=generation_id,
            status="succeeded",
            output_url=result.output_url,
        )


def enqueue_generation(generation_id: uuid.UUID) -> None:
    worker = threading.Thread(
        target=run_generation,
        args=(generation_id,),
        daemon=True,
        name=f"app-generation-{generation_id}",
    )
    worker.start()
