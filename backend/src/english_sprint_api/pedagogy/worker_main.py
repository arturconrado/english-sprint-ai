from __future__ import annotations

import asyncio
import socket

from english_sprint_api.config import get_settings
from english_sprint_api.pedagogy.content_store import TransientTranscriptStore
from english_sprint_api.pedagogy.missions import MissionCatalog
from english_sprint_api.pedagogy.openai_evaluation import OpenAIResponsesEvaluationProvider
from english_sprint_api.pedagogy.queue import ConversationQueue, EvaluationQueue
from english_sprint_api.pedagogy.repository import MissionRepository
from english_sprint_api.pedagogy.worker import AttemptEvaluator, run_worker


async def main() -> None:
    settings = get_settings()
    if not settings.pedagogy_enabled:
        raise RuntimeError("PEDAGOGY_ENABLED must be true for the evaluator worker.")
    if not settings.pedagogy_configuration_valid:
        raise RuntimeError("Pedagogy worker configuration is incomplete.")
    if settings.content_encryption_key is None:
        raise RuntimeError("CONTENT_ENCRYPTION_KEY is required.")
    repository = MissionRepository(settings.database_url)
    queue = EvaluationQueue(settings.redis_url)
    transcripts = TransientTranscriptStore(
        settings.redis_url,
        settings.content_encryption_key.get_secret_value(),
        settings.content_encryption_key_version,
        settings.pedagogy_content_ttl_seconds,
    )
    provider = OpenAIResponsesEvaluationProvider(settings)
    conversation_queue = ConversationQueue(settings.redis_url)
    evaluator = AttemptEvaluator(
        repository,
        transcripts,
        provider,
        conversation_queue,
    )
    await repository.sync_catalog(MissionCatalog())
    await queue.ensure_group()
    try:
        await run_worker(queue, evaluator, f"{socket.gethostname()}-{id(evaluator)}")
    finally:
        await transcripts.close()
        await conversation_queue.close()
        await queue.close()


if __name__ == "__main__":
    asyncio.run(main())
