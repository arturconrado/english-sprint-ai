from typing import Protocol
from uuid import UUID

from english_sprint_api.pedagogy.evaluation import AttemptEvaluation


class ConversationProvider(Protocol):
    async def present(self, session_id: UUID, instruction: str) -> str: ...

    async def stop_response(self, session_id: UUID) -> None: ...


class AttemptTranscriptionProvider(Protocol):
    async def completed_transcript(self, attempt_id: UUID) -> str | None: ...


class AttemptEvaluationProvider(Protocol):
    async def evaluate(
        self,
        attempt_id: UUID,
        transcript: str,
        mission_context: str,
    ) -> AttemptEvaluation: ...


class MissionSummaryProvider(Protocol):
    async def summarize(self, session_id: UUID) -> str: ...
