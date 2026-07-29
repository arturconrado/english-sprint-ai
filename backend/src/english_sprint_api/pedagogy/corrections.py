from english_sprint_api.pedagogy.evaluation import CorrectionCandidate


def select_corrections(
    candidates: tuple[CorrectionCandidate, ...],
) -> tuple[CorrectionCandidate, ...]:
    ordered = sorted(
        candidates,
        key=lambda item: (-item.priority, item.category, item.original),
    )
    primary = next(
        (item for item in ordered if item.priority >= 0.55 and item.confidence >= 0.65),
        None,
    )
    if primary is None:
        return ()
    secondary = next(
        (
            item
            for item in ordered
            if item is not primary
            and item.cause != primary.cause
            and item.priority >= 0.70
            and item.confidence >= 0.75
        ),
        None,
    )
    return (primary,) if secondary is None else (primary, secondary)


class CorrectionComposer:
    @staticmethod
    def compose(correction: CorrectionCandidate) -> str:
        return (
            f'One important correction: instead of "{correction.original}", '
            f'say "{correction.recommended}". {correction.explanation} '
            "Now answer again in your own words."
        )
