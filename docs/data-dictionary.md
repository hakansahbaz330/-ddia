# Veri sözlüğü

| Tablo | Amaç |
|---|---|
| `import_runs` | Her içe aktarma: dosya, SHA-256, durum, kullanılan eşleşme, JSON rapor |
| `teams`, `team_aliases` | Takımlar (ülke+ad tekil); onaylı yazım eşleşmeleri |
| `matches` | Maç: lig, ülke, sezon, tarih/saat, takımlar, FT/HT skor, sonuç (H/D/A), hakem, Asya handikap çizgileri |
| `odds_sources` | Oran sütunu sözlüğü: bahisçi, pazar (1X2/OU/AH), seçim, çizgi, tür (pre/closing/unspecified) |
| `odds_history` | (maç, kaynak, oran, import çalışması) — spec'teki düz görünüm: `odds_history_view` |
| `team_match_stats` | Takım başına: şut, isabetli şut, faul, korner, sarı/kırmızı, serbest vuruş, xG (olanlar) |
| `team_strength_history`, `predictions`, `backtest_runs`, `coupons` | Şema hazır; Faz 4–7'de doldurulacak (şu an boş) |
| `data_quality_logs` | Satır bazlı uyarı/hata örnekleri |

`matches.ft_result/ht_result`: H=ev, D=beraberlik, A=deplasman. `recorded_at` her zaman NULL'dır (kaynakta yok).
