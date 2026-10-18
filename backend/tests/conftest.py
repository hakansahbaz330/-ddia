import csv
from datetime import datetime
from pathlib import Path

import openpyxl
import pytest
from sqlalchemy.orm import sessionmaker

from app.db import make_engine
from app.schema import Base

HEADER = ["Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR", "HTHG", "HTAG", "HS", "AS", "B365H", "B365D",
          "B365A", "B365CH", "B365CD", "B365CA", "B365>2.5", "B365<2.5", "AHh", "Weird"]


def rows():
    d = datetime(2023, 8, 12)
    return [
        ["E0", d, "Arsenal", "Chelsea", 2, 1, None, 1, 0, 12, 8, 2.0, 3.4, 3.8, 1.9, 3.5, 4.0, 1.8, 2.0, -0.5, "x"],
        ["E0", datetime(2023, 8, 13), "Everton", "Fulham", 0, 0, None, 0, 0, 5, 6, 2.5, 3.2, 3.0, 2.4, 3.2, 3.1, 2.2, 1.7, 0, "x"],
        ["D1", d, "Bayern", "Köln", 4, 0, None, 2, 0, None, None, 1.1, 9.0, 20.0, None, None, None, None, None, None, "x"],
    ]


@pytest.fixture
def session():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as s:
        yield s


@pytest.fixture
def xlsx(tmp_path) -> Path:
    p = tmp_path / "all-euro-data-2023-2024.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "E0"
    ws.append(HEADER)
    for r in rows():
        ws.append(r)
    wb.save(p)
    return p


@pytest.fixture
def csv_file(tmp_path) -> Path:
    p = tmp_path / "arsiv-2023-2024.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for r in rows():
            w.writerow([r[0], r[1].strftime("%d/%m/%Y")] + ["" if v is None else v for v in r[2:]])
    return p
