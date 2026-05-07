from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    openai_api_key: Optional[SecretStr] = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", validation_alias="OPENAI_MODEL")
    openai_provider: str = Field(default="openai", validation_alias="OPENAI_PROVIDER")
    mock_llm: bool = Field(default=False, validation_alias="MOCK_LLM")
    fetch_timeout_seconds: int = Field(default=30, validation_alias="FETCH_TIMEOUT_SECONDS")
    max_chars_per_llm_batch: int = Field(default=60_000, validation_alias="MAX_CHARS_PER_LLM_BATCH")
    max_section_chars: int = Field(default=3_500, validation_alias="MAX_SECTION_CHARS")
    output_dir: Path = Field(default=Path("."), validation_alias="OUTPUT_DIR")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_file: str = Field(default="pipeline.log", validation_alias="LOG_FILE")
    source_file: Path = Field(default=Path("sources.json"), validation_alias="SOURCE_FILE")
    previous_snapshot_file: Path = Field(
        default=Path("previous_snapshot_document_a.txt"),
        validation_alias="PREVIOUS_SNAPSHOT_FILE",
    )
    run_state_file: Path = Field(default=Path("run_state.json"), validation_alias="RUN_STATE_FILE")

    @property
    def api_key_value(self) -> str | None:
        return self.openai_api_key.get_secret_value() if self.openai_api_key else None
