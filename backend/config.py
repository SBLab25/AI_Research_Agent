"""
Application configuration — stores API keys in memory (set via UI).
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AppConfig:
    """Runtime configuration managed through the UI settings panel."""

    # LLM Configuration
    openai_api_key: Optional[str] = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    # arXiv needs no key
    max_papers: int = 15

    def is_configured(self) -> bool:
        """Check if the minimum required API keys are set."""
        return bool(self.openai_api_key)

    def update(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self, key) and value is not None:
                setattr(self, key, value)


# Global singleton
config = AppConfig()
