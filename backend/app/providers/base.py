"""Canlı veri sağlayıcı arayüzü. Her sağlayıcı yalnızca lisanslı/resmi API veya kullanıcının kendi girdisini kullanır."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


class ProviderError(Exception):
    """Kullanıcıya gösterilebilir sağlayıcı hatası (anahtar yok, kota, ağ ...)."""

    def __init__(self, message: str, code: str = "provider_error"):
        super().__init__(message)
        self.code = code


@dataclass
class LiveOdd:
    bookmaker: str
    market: str  # 1X2 | OU2.5
    selection: str  # 1,X,2 | over,under
    odds: float
    source_updated_at: datetime | None = None


@dataclass
class LiveFixture:
    provider: str
    ext_id: str
    sport_key: str
    league_title: str
    home: str
    away: str
    commence_time: datetime
    odds: list[LiveOdd] = field(default_factory=list)


@dataclass
class FetchResult:
    fixtures: list[LiveFixture]
    requests_remaining: int | None = None
    requests_used: int | None = None


class OddsProvider(Protocol):
    name: str
    terms_url: str
    license_note: str

    def fetch(self, sport_keys: list[str]) -> FetchResult: ...
