from dataclasses import dataclass


@dataclass(slots=True)
class RealtimeError(Exception):
    code: str
    title: str
    status: int
    detail: str
    retryable: bool = False


class ProviderError(RealtimeError):
    def __init__(
        self,
        *,
        code: str = "provider_error",
        status: int = 502,
        detail: str = "The realtime provider could not create the call.",
        retryable: bool = True,
    ) -> None:
        super().__init__(
            code=code,
            title="Realtime provider failure",
            status=status,
            detail=detail,
            retryable=retryable,
        )
