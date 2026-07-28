import base64
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid4

from english_sprint_api.pedagogy.evaluation import AttemptEvaluation, CorrectionCandidate
from english_sprint_api.pedagogy.openai_evaluation import EvaluationResult, ModelUsage
from english_sprint_api.pedagogy.repository import EvaluationWorkRecord
from english_sprint_api.pedagogy.worker import AttemptEvaluator


class FakeConversationQueue:
    def __init__(self) -> None:
        self.enqueued: list[UUID] = []

    async def enqueue(self, attempt_id: UUID) -> None:
        self.enqueued.append(attempt_id)


class FakeTranscripts:
    def __init__(self, transcript: str | None) -> None:
        self.transcript = transcript
        self.deleted: list[UUID] = []
        self.instructions: dict[UUID, str] = {}

    async def get(self, attempt_id: UUID) -> str | None:
        del attempt_id
        return self.transcript

    async def delete(self, attempt_id: UUID) -> None:
        self.deleted.append(attempt_id)

    async def put_instruction(self, attempt_id: UUID, instruction: str) -> None:
        self.instructions[attempt_id] = instruction


class FakeRepository:
    def __init__(self, attempt_id: UUID) -> None:
        self.attempt_id = attempt_id
        self.saved: EvaluationResult | None = None

    async def evaluation_work(self, attempt_id: UUID) -> EvaluationWorkRecord:
        assert attempt_id == self.attempt_id
        return EvaluationWorkRecord(attempt_id, "mission", {})

    async def save_evaluation(
        self,
        result: EvaluationResult,
        selected: tuple[CorrectionCandidate, ...],
    ) -> None:
        del selected
        self.saved = result

    async def fail_evaluation(self, attempt_id: UUID, terminal: bool) -> None:
        del attempt_id, terminal


@dataclass
class FakeProvider:
    result: EvaluationResult

    async def evaluate(
        self,
        attempt_id: UUID,
        transcript: str,
        mission_context: str,
        recurrence_by_category: dict[str, float] | None = None,
    ) -> EvaluationResult:
        del attempt_id, transcript, mission_context, recurrence_by_category
        return self.result


async def test_evaluator_requires_matching_attempt_and_deletes_transcript() -> None:
    attempt_id = uuid4()
    evaluation = AttemptEvaluation(
        schema_version="1.0",
        attempt_id=attempt_id,
        understood=True,
        response_completed=True,
        dimensions={},
        candidate_corrections=(),
        strengths=(),
        missing_elements=(),
    )
    result = EvaluationResult(
        evaluation,
        ModelUsage(
            "gpt-5.4-mini-2026-03-17",
            1,
            2,
            0,
            0,
            5,
            Decimal("0.00000975"),
        ),
    )
    repository = FakeRepository(attempt_id)
    transcripts = FakeTranscripts("A completed answer.")
    conversation_queue = FakeConversationQueue()
    evaluator = AttemptEvaluator(
        repository,
        transcripts,
        FakeProvider(result),
        conversation_queue,
    )

    await evaluator.evaluate(attempt_id)

    assert repository.saved == result
    assert transcripts.deleted == [attempt_id]
    assert conversation_queue.enqueued == [attempt_id]


def test_content_key_fixture_is_256_bits() -> None:
    fixture = base64.urlsafe_b64encode(bytes(range(32))).decode().rstrip("=")
    assert len(base64.urlsafe_b64decode(fixture + "=" * (-len(fixture) % 4))) == 32
