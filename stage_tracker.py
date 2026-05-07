from __future__ import annotations

from constants import STAGE_ORDER, Stage


class StageTracker:
    def __init__(self) -> None:
        self.current = Stage.INIT
        self.completed: list[str] = [Stage.INIT.value]

    def advance(self, next_stage: Stage) -> None:
        current_index = STAGE_ORDER.index(self.current)
        expected = STAGE_ORDER[current_index + 1]
        if next_stage != expected:
            raise RuntimeError(
                f"Invalid stage transition from {self.current.value} to {next_stage.value}; "
                f"expected {expected.value}"
            )
        self.current = next_stage
        self.completed.append(next_stage.value)
