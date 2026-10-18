"""The Odds API (v4) bağlayıcısı. Anahtar yalnızca ortam değişkeninden (ODDS_API_KEY) okunur.

Doğrulanan yapı (the-odds-api.com/liveapi/guides/v4): GET /v4/sports/{sport}/odds?regions=&markets=&oddsFormat=decimal&apiKey=
Yanıt: [{id, sport_key, commence_time, home_team, away_team, bookmakers:[{key,title,last_update,markets:[{key,outcomes:[{name,price,point?}]}]}]}]
Kota: istek başına bölge×pazar kredisi. Hangi bahisçilerin (ör. bet365) hangi bölgede yer aldığı hesabınıza/planınıza bağlıdır;
bu kodda doğrulanmış bir iddia yoktur — dönen bahisçi listesini olduğu gibi saklarız.
Canlı çağrı bu ortamda anahtar olmadığından denenmedi; ayrıştırma örnek yanıtlarla test edilir.
"""
from __future__ import annotations

from datetime import datetime

import httpx

from app.providers.base import FetchResult, LiveFixture, LiveOdd, ProviderError

BASE = "https://api.the-odds-api.com"


def _dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)


def parse_events(events: list[dict], sport_key: str = "", league_title: str = "") -> list[LiveFixture]:
    out = []
    for ev in events:
        fx = LiveFixture(provider="the_odds_api", ext_id=str(ev["id"]), sport_key=ev.get("sport_key", sport_key),
                         league_title=league_title or ev.get("sport_title", ""), home=ev["home_team"], away=ev["away_team"],
                         commence_time=_dt(ev["commence_time"]))
        for bk in ev.get("bookmakers", []):
            upd = _dt(bk.get("last_update"))
            for mk in bk.get("markets", []):
                if mk["key"] == "h2h":
                    names = {ev["home_team"]: "1", ev["away_team"]: "2", "Draw": "X"}
                    for o in mk["outcomes"]:
                        if o["name"] in names and o.get("price", 0) > 1:
                            fx.odds.append(LiveOdd(bk["key"], "1X2", names[o["name"]], float(o["price"]), upd))
                elif mk["key"] == "totals":
                    for o in mk["outcomes"]:
                        if o.get("point") == 2.5 and o["name"] in ("Over", "Under") and o.get("price", 0) > 1:
                            fx.odds.append(LiveOdd(bk["key"], "OU2.5", o["name"].lower(), float(o["price"]), upd))
        out.append(fx)
    return out


class OddsApiProvider:
    name = "the_odds_api"
    terms_url = "https://the-odds-api.com/terms-and-conditions.html"
    license_note = "Ücretli/kotalı lisanslı API. Kullanım koşulları ve plan limitleri hesabınıza bağlıdır; verileri yeniden dağıtmayın."

    def __init__(self, api_key: str, regions: str = "eu", client: httpx.Client | None = None):
        if not api_key:
            raise ProviderError("ODDS_API_KEY tanımlı değil. .env dosyasına anahtarınızı ekleyin veya bülteni elle yapıştırın.", "no_key")
        self.key, self.regions = api_key, regions
        self.client = client or httpx.Client(timeout=15)

    def _get(self, path: str, params: dict) -> httpx.Response:
        try:
            r = self.client.get(BASE + path, params={**params, "apiKey": self.key})
        except httpx.HTTPError as exc:
            raise ProviderError(f"Sağlayıcıya ulaşılamadı: {exc.__class__.__name__}", "network") from exc
        if r.status_code == 401:
            raise ProviderError("API anahtarı geçersiz veya yetkisiz (401).", "bad_key")
        if r.status_code == 429:
            raise ProviderError("İstek sınırı/kotası aşıldı (429). Bir süre sonra deneyin veya planınızı kontrol edin.", "quota")
        if r.status_code >= 400:
            raise ProviderError(f"Sağlayıcı hata döndürdü ({r.status_code}).", "http_error")
        return r

    def list_soccer_sports(self) -> list[dict]:
        r = self._get("/v4/sports/", {})
        return [s for s in r.json() if str(s.get("key", "")).startswith("soccer")]

    def fetch(self, sport_keys: list[str]) -> FetchResult:
        fixtures, remaining, used = [], None, None
        for sk in sport_keys:
            r = self._get(f"/v4/sports/{sk}/odds", {"regions": self.regions, "markets": "h2h,totals", "oddsFormat": "decimal"})
            fixtures += parse_events(r.json(), sport_key=sk)
            remaining = int(r.headers["x-requests-remaining"]) if "x-requests-remaining" in r.headers else remaining
            used = int(r.headers["x-requests-used"]) if "x-requests-used" in r.headers else used
        return FetchResult(fixtures, remaining, used)
