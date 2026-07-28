from __future__ import annotations

import asyncio
from typing import Protocol
from uuid import UUID

from english_sprint_api.pedagogy.corrections import select_corrections
from english_sprint_api.pedagogy.evaluation import CorrectionCandidate
from english_sprint_api.pedagogy.openai_evaluation import (
    EvaluationResult,
    OpenAIResponsesEvaluationProvider,
)
from english_sprint_api.pedagogy.queue import EvaluationQueue
from english_sprint_api.pedagogy.repository import EvaluationWorkRecord


class EvaluationRepository(Protocol):
    async def evaluation_work(self, attempt_id: UUID) -> EvaluationWorkRecord: ...

    async def save_evaluation(
        self,
        result: EvaluationResult,
        selected: tuple[CorrectionCandidate, ...],
    ) -> None: ...

    async def fail_evaluation(self, attempt_id: UUID, terminal: bool) -> None: ...


class EvaluationProvider(Protocol):
    async def evaluate(
        self,
        attempt_id: UUID,
        transcript: str,
        mission_context: str,
        recurrence_by_category: dict[str, float] | None = None,
    ) -> EvaluationResult: ...


class TranscriptStore(Protocol):
    async def get(self, attempt_id: UUID) -> str | None: ...

    async def delete(self, attempt_id: UUID) -> None: ...


class AttemptEvaluator:
    def __init__(
        self,
        repository: EvaluationRepository,
        transcripts: TranscriptStore,
        provider: EvaluationProvider,
    ) -> None:
        self._repository = repository
        self._transcripts = transcripts
        self._provider = provider

    async def evaluate(self, attempt_id: UUID) -> None:
        work = await self._repository.evaluation_work(attempt_id)
        transcript = await self._transcripts.get(attempt_id)
        if transcript is None:
            raise RuntimeError("completed_transcript_unavailable")
        result = await self._provider.evaluate(
            attempt_id,
            transcript,
            work.mission_context,
            work.recurrence_by_category,
        )
        if result.evaluation.attempt_id != attempt_id:
            raise RuntimeError("evaluation_attempt_mismatch")
        selected = select_corrections(result.evaluation.candidate_corrections)
        await self._repository.save_evaluation(result, selected)
        await self._transcripts.delete(attempt_id)

    async def fail(self, attempt_id: UUID, terminal: bool) -> None:
        await self._repository.fail_evaluation(attempt_id, terminal)


async def run_worker(
    queue: EvaluationQueue,
    evaluator: AttemptEvaluator,
    consumer: str,
) -> None:
    while True:
        processed = await queue.consume_once(
            consumer,
            evaluator.evaluate,
            evaluator.fail,
        )
        if not processed:
            await asyncio.sleep(0.25)


def ensure_provider_type(
    provider: OpenAIResponsesEvaluationProvider,
) -> EvaluationProvider:
    return provider
