# Arşiv inceleme bulguları (Faz 1)

Kaynak: 10 adet Football-Data.co.uk "all-euro-data" Excel dosyası (2017-18 … 2026-27), her biri 22 lig sayfası.
Gerçek veri: **70.428 maç**, 2017-07-28 → 2026-10-14, **562 takım**, 22 lig (İngiltere 1–5, İskoçya 1–4, Almanya, İspanya,
İtalya, Fransa 1–2, Hollanda, Belgika, Portekiz, Türkiye, Yunanistan). **~9 sezon** (2026-27 yalnızca 1.088 maç, kısmi) — 10 yıl değil.
Her dosyada 22 sayfa; dosya başına 6.904–7.830 maç (2019-20 COVID nedeniyle az).

| Konu | Bulgu |
|---|---|
| Skorlar | Maç sonu skoru 69.918 maçta var (2 maçta yok: G1 2019-03-17 Panathinaikos–Olympiakos, F2 2025-12-05 Bastia–Red Star). İlk yarı skoru 69.852 maçta. |
| FTR/HTR | Excel formülü; kullanılmadı, skordan hesaplandı (2023-24 için kaynak FTR ile birebir aynı çıktı). |
| 1X2 oranı | Tüm sezonlarda var. Pre: B365, BW, IW, PS, WH, VC (+LB 2017-18 ve 2025-26), Max/Avg 2019-20'den; 2024 sonrası BF/BFE/1XB/BMGM/BV/CL/PP/SKB. Kapanış (C): 2017-19'da yalnız Pinnacle, 2019-20'den itibaren çok bahisçi. |
| Üst/Alt | Yalnızca **2,5 gol** çizgisi: 2017-19'da yalnız BetBrain en yüksek/ortalama; 2019-20'den B365, Pinnacle, Max, Avg (+BFE 2024'ten). **1,5/3,5 yok.** |
| Asya handikap | Var (çizgi + oranlar); ana ürün pazarı değil. |
| **Türetilen gerçekleşmiş sonuçlar** | Skor/istatistiklerden **her maç için** hesaplanıp `match_outcomes` tablosuna yazıldı (`app/markets.py`): 1X2, çifte şans, 0,5–5,5 üst/alt, karşılıklı gol, tek/çift, takım gol çizgileri, gol yemeden kazanma, İY 1X2 / 0,5–2,5 üst-alt / karşılıklı gol, İY/MS (9 kombinasyon), 2. yarı sonuç ve gol çizgileri, hangi yarı daha golcü, kesin skor, korner ve kart toplamı üst/alt. Bunlar arşivdeki skorlardan *kesin* hesaplanır; oran gerektirmez. |
| **Oranı olmayan pazarlar** | Yukarıdaki pazarların çoğunun (1,5/3,5 üst-alt, karşılıklı gol, İY, İY/MS, korner, kart) **bahis oranı** arşivde yok. Bu yalnızca *piyasa olasılığı* ve *EV* hesabını etkiler: bu pazarlarda model olasılığı üretilir ve gerçekleşme sıklıklarıyla test edilir, ama marjdan arındırılmış piyasa olasılığı ve EV hesaplanamaz (canlı oran API'si Faz 6'da bunu tamamlayabilir). |
| Oran zamanı | Zaman damgası yok. C'siz sütunlar "maç öncesi (zamanı belirsiz)", C'li "kapanış" kabul edildi; kesin değildir. |
| İstatistik | Şut/isabetli şut/korner: 65.101 maç; faul 63.761; sarı/kırmızı ~69.850; serbest vuruş 1.334 maç; **xG yalnızca 2026-27 sezonunda, 893 maç**. Kadro/dinlenme verisi yok. |
| Hatalı oranlar | 50 oran ≤1.00 (çoğu 0.0) → atlandı ve loglandı. |
| Tekrar | Dosya içi/dosyalar arası tekrar yok, skor çakışması yok. |
| Takım adları | Sezonlar arası yazım tutarlı; benzer çiftler (Barcelona/Barcelona B, Reggina/Reggiana…) gerçekten farklı takımlar, birleştirilmedi. |
