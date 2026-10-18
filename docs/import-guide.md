# Arşiv içe aktarma kılavuzu

## Desteklenen girdi
`.xlsx/.xlsm` (tüm sayfalar; her sayfa bir lig) ve `.csv` (UTF-8/Windows-1254/Latin-1; `,` `;` sekme ayracı). Dosya satır satır
akıtılır, 1500 satırlık parçalar halinde yazılır. Sezon dosya adındaki `YYYY-YYYY` kalıbından alınır (yoksa tarihten: Temmuz+ = yeni sezon).

## Sütun eşleştirme
Otomatik: Football-Data.co.uk şeması (çekirdek alanlar, `HS/AS…` istatistikleri, `<bahisçi>[C]<H|D|A | >2.5 | AHH>` oranları, `Bb*` toplamları).
Sütun adındaki **C** harfi = kapanış oranı (`closing`), yoksa `pre`; BetBrain (`Bb*`) için `unspecified`.
**Kaynak dosyalarda oran zaman damgası yoktur**; `pre` kesin açılış oranı değildir, kapanış da yalnızca sütun adına dayanır.

Tanınmayan sütunlar içe aktarılmaz ve raporda listelenir. Elle düzeltme için JSON:
```json
{"Gizemli": "odds:B365:1X2:H:closing", "Not": "ignore", "Ev": "core:home_team", "Sut": "stat:shots:H", "X": "odds:PS:OU2.5:over:pre"}
```
`POST /api/imports/preview` ile önce otomatik eşleşmeyi görün, sonra `mapping` alanıyla `POST /api/imports` çağırın.

## Doğrulama kuralları
- Tarih okunamıyor / takım boş / ev=deplasman → satır **reddedilir** (`data_quality_logs`).
- Skor geçersiz (negatif, >30, sayısal değil) veya yalnız tek taraf → **boş (NULL)** bırakılır, 0 yapılmaz.
- İlk yarı skoru > maç sonu → ilk yarı skoru boşaltılır. Skor yoksa maç "sonuçsuz" kaydedilir.
- Oran ≤ 1.00, > 1000 veya sayısal değil → o oran atlanır ve loglanır (boş hücre sessizce atlanır).
- `FTR/HTR` Excel formülü olduğundan kullanılmaz; sonuç skordan hesaplanır.

## Tekrarlar
Maç kimliği `sha1(lig|tarih|ev|deplasman)`. Aynı dosya (SHA-256) tekrar yüklenirse atlanır (`force` ile aşılır).
Aynı maç başka dosyada/çalışmada geçerse maç tekrarlanmaz; **oranlar yeni gözlem olarak eklenir** (silinmez).
Skorlar çelişirse veritabanındaki korunur, çakışma loglanır. Takım adı yazım farkları otomatik birleştirilmez:
`GET /api/teams/alias-suggestions` aday gösterir, `POST /api/teams/aliases` ile onaylarsınız.

## Rapor
`import_runs.report` (JSON) ve CLI çıktısı: bulunan satır, aktarılan/mevcut/tekrar/çakışan/reddedilen sayıları, red nedenleri,
lig×sezon dağılımı, pazar×bahisçi kapsamı, tanınmayan sütunlar, uyarı toplamları. Her uyarı türü için ilk 50 örnek satır
`data_quality_logs` tablosundadır (toplam sayı raporda).
