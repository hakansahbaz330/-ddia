from sqlalchemy import func, select

from app.importer.engine import import_file
from app.schema import DataQualityLog, Match, OddsHistory, TeamMatchStat


def test_xlsx_import_counts_and_report(session, xlsx):
    rep = import_file(session, xlsx)
    assert rep["status"] == "ok"
    assert rep["rows_found"] == 3 and rep["matches_imported"] == 3
    assert rep["unknown_columns"] == ["Weird"]
    assert set(rep["markets"]) == {"1X2", "OU"}
    m = session.scalar(select(Match).where(Match.home_team == "Arsenal"))
    assert (m.season, m.country, m.ft_result, m.ht_result, m.ah_line) == ("2023-2024", "England", "H", "H", -0.5)
    # Bayern satırında kapanış oranı boş: oran satırı üretilmemeli (0'a çevrilmemeli)
    bayern = session.scalar(select(Match).where(Match.home_team == "Bayern"))
    n = session.scalar(select(func.count()).select_from(OddsHistory).where(OddsHistory.match_id == bayern.id))
    assert n == 3
    assert session.scalar(select(func.count()).select_from(TeamMatchStat)) == 4  # Bayern için istatistik yok


def test_same_file_is_skipped_and_force_does_not_duplicate_matches(session, xlsx):
    import_file(session, xlsx)
    again = import_file(session, xlsx)
    assert again["status"] == "skipped"
    forced = import_file(session, xlsx, force=True)
    assert forced["already_in_db"] == 3 and forced["matches_imported"] == 0
    assert session.scalar(select(func.count()).select_from(Match)) == 3
    # farklı çalışma = yeni oran gözlemi olarak korunur (gözlemler tekrar sanılıp silinmez)
    assert session.scalar(select(func.count()).select_from(OddsHistory)) > 0


def test_csv_and_excel_give_same_result(session, xlsx, csv_file):
    a = import_file(session, xlsx)
    assert a["matches_imported"] == 3
    b = import_file(session, csv_file)  # aynı maçlar: hepsi zaten var
    assert b["status"] == "ok" and b["already_in_db"] == 3 and b["conflicts"] == 0


def test_duplicates_and_bad_rows_in_file(session, tmp_path):
    import openpyxl
    from tests.conftest import HEADER, rows
    p = tmp_path / "x-2023-2024.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEADER)
    r = rows()
    ws.append(r[0])
    ws.append(r[0])  # birebir tekrar
    ws.append(r[0][:4] + [3, 3] + r[0][6:])  # aynı maç, farklı skor
    ws.append(["E0", "bozuk tarih"] + r[0][2:])  # geçersiz tarih
    wb.save(p)
    rep = import_file(session, p)
    assert rep["matches_imported"] == 1
    assert rep["duplicates_in_file"] == 2 and rep["conflicts"] == 1
    assert rep["rows_rejected"] == 1 and rep["reject_reasons"] == {"invalid_date": 1}
    assert session.scalar(select(func.count()).select_from(DataQualityLog)
                          .where(DataQualityLog.issue_type == "conflict_in_file")) == 1


def test_user_mapping_override_imports_unknown_column(session, xlsx):
    rep = import_file(session, xlsx, overrides={"Weird": "ignore"})
    assert rep["unknown_columns"] == []


def test_unsupported_and_corrupt_files_fail_cleanly(session, tmp_path):
    bad = tmp_path / "bozuk-2023-2024.xlsx"
    bad.write_bytes(b"bu bir excel degil")
    rep = import_file(session, bad)
    assert rep["status"] == "failed" and "açılamadı" in rep["error"]
    txt = tmp_path / "a.pdf"
    txt.write_bytes(b"%PDF")
    assert import_file(session, txt)["status"] == "failed"
    assert session.scalar(select(func.count()).select_from(Match)) == 0


def test_missing_required_columns_sheet_skipped(session, tmp_path):
    import openpyxl
    p = tmp_path / "y-2023-2024.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Foo", "Bar"])
    ws.append([1, 2])
    wb.save(p)
    rep = import_file(session, p)
    assert rep["matches_imported"] == 0 and rep["sheets"][0]["skipped"]
