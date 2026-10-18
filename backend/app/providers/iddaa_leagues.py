"""İddaa bülten lig kodu -> arşiv lig kodu (Football-Data). Yalnızca arşivdeki ligler uygulamaya alınır.

Eşleme, 16-19 Ekim 2026 bülteninde her kodun takımlarının arşivdeki lige ait takımlarla eşleşmesine bakılarak elle doğrulandı
(ör. SÜPL=Süper Lig: Çorum, Erzurumspor, Amed arşivin T1 sayfasında; T1L=TFF 1. Lig: arşivde yok).
Tanınmayan kodlar sessizce atılmaz: `excluded` içinde sayıları döner. Yeni bir kod gerekirse buraya ekleyin.
"""
from __future__ import annotations

from collections import Counter

IDDAA_TO_ARCHIVE = {
    "İNP": "E0", "İNCH": "E1", "İN1": "E2", "İN2": "E3",
    "İSKOP": "SC0", "İSKCH": "SC1", "İSKO1": "SC2", "İSKO2": "SC3",
    "ALBU": "D1", "AL2B": "D2", "İSPL1": "SP1", "İSPL2": "SP2", "İTSA": "I1", "İTSB": "I2",
    "FR1": "F1", "FR2": "F2", "HOLL": "N1", "SÜPL": "T1", "YUN": "G1",
    # İFAK = FA Kupası (Atherton Collieries gibi alt lig takımları var; arşivdeki National League değil) -> bilinçli olarak yok.
    # EC (National League) bu bültende lig olarak görülmedi.
    # Arşivde olan ama bu bültende görülmeyen ligler için olası kodlar (doğrulanmadı, bu yüzden boş bırakıldı): B1 Belçika, P1 Portekiz.
}
ARCHIVE_DIVISIONS = {
    "E0": "Premier League", "E1": "Championship", "E2": "League One", "E3": "League Two", "EC": "National League",
    "SC0": "Premiership", "SC1": "Championship (İskoçya)", "SC2": "League One (İskoçya)", "SC3": "League Two (İskoçya)",
    "D1": "Bundesliga", "D2": "2. Bundesliga", "SP1": "La Liga", "SP2": "Segunda División", "I1": "Serie A", "I2": "Serie B",
    "F1": "Ligue 1", "F2": "Ligue 2", "N1": "Eredivisie", "B1": "Pro League", "P1": "Primeira Liga", "T1": "Süper Lig", "G1": "Süper Lig (Yunanistan)",
}


def filter_archive_leagues(matches: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """Arşivdeki liglere ait maçları `division` alanıyla döndürür; diğerlerinin kod başına sayısını `excluded` olarak verir."""
    kept, excluded = [], Counter()
    for m in matches:
        div = IDDAA_TO_ARCHIVE.get(m["league"])
        if div is None:
            excluded[m["league"] or "?"] += 1
            continue
        kept.append({**m, "division": div})
    return kept, dict(excluded.most_common())
