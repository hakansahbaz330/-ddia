"""İçe aktarma raporunu okunabilir Türkçe metne çevirir."""


def render_report(rep: dict) -> str:
    if rep.get("status") == "skipped":
        return f"[ATLANDI] {rep['file']}: {rep['message']}"
    if rep.get("status") == "failed":
        return f"[HATA] {rep['file']}: {rep.get('error')}"
    L = [f"=== {rep['file']} (çalışma #{rep.get('run_id')}) ===",
         f"Bulunan toplam satır      : {rep['rows_found']}",
         f"Aktarılan yeni maç        : {rep['matches_imported']}",
         f"Veritabanında zaten vardı : {rep['already_in_db']}",
         f"Dosya içi tekrar          : {rep['duplicates_in_file']}",
         f"Skor çakışması            : {rep['conflicts']}",
         f"Reddedilen satır          : {rep['rows_rejected']} {rep['reject_reasons'] or ''}",
         f"Skoru olan / olmayan maç  : {rep['matches_with_ft_score']} / {rep['matches_without_score']}",
         f"İlk yarı skoru olan maç   : {rep['matches_with_ht_score']}",
         f"Aktarılan oran satırı     : {rep['odds_rows_inserted']}",
         f"Takım istatistiği satırı  : {rep['stat_rows_inserted']}",
         f"Tarih aralığı             : {rep['date_range'][0]} → {rep['date_range'][1]}"]
    if rep["unknown_columns"]:
        L.append(f"Tanınmayan sütunlar       : {', '.join(rep['unknown_columns'])}")
    if rep["issue_totals"]:
        L.append("Veri kalitesi uyarıları   : " + ", ".join(f"{k}={v}" for k, v in sorted(rep["issue_totals"].items())))
    L.append("Pazarlar                  : " + "; ".join(f"{m} ({len(v)} kaynak)" for m, v in rep["markets"].items()))
    L.append(f"Lig sayısı                : {len(rep['league_season_counts'])}")
    return "\n".join(L)
