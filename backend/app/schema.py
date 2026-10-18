"""Veritabanı şeması (SQLAlchemy 2). SQLite ve PostgreSQL ile uyumludur.

Oranlar uzun formatta (odds_history) tutulur; sütun anlamı `odds_sources` sözlük
tablosundadır (bahis şirketi, pazar, seçim, çizgi, oran türü). Böylece milyonlarca
satırda metin tekrarlanmaz. `odds_history_view` spesifikasyondaki düz görünümü verir.
"""
from datetime import date, datetime, time

from sqlalchemy import (
    Column,
    Table,
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ImportRun(Base):
    __tablename__ = "import_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    file_size: Mapped[int] = mapped_column(Integer)
    season_hint: Mapped[str | None] = mapped_column(String(9))
    status: Mapped[str] = mapped_column(String(16), default="running")  # running/ok/failed
    mapping: Mapped[dict | None] = mapped_column(JSON)  # kullanılan sütun eşleşmesi
    report: Mapped[dict | None] = mapped_column(JSON)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("country", "name", name="uq_team_country_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    country: Mapped[str] = mapped_column(String(40), default="")


class TeamAlias(Base):
    """Kullanıcı onaylı takım adı eşleşmeleri (aynı takımın farklı yazımları)."""

    __tablename__ = "team_aliases"
    alias: Mapped[str] = mapped_column(String(100), primary_key=True)
    country: Mapped[str] = mapped_column(String(40), primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        Index("ix_matches_date", "match_date"),
        Index("ix_matches_div_season", "division", "season"),
        Index("ix_matches_home", "home_team_id", "match_date"),
        Index("ix_matches_away", "away_team_id", "match_date"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    match_key: Mapped[str] = mapped_column(String(40), unique=True)  # sha1(div|tarih|ev|dep)
    division: Mapped[str] = mapped_column(String(8))
    country: Mapped[str | None] = mapped_column(String(40))
    league_name: Mapped[str | None] = mapped_column(String(60))
    tier: Mapped[int | None] = mapped_column(SmallInteger)
    season: Mapped[str] = mapped_column(String(9))  # "2023-2024"
    match_date: Mapped[date] = mapped_column(Date)
    kickoff_time: Mapped[time | None] = mapped_column(Time)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    home_team: Mapped[str] = mapped_column(String(100))
    away_team: Mapped[str] = mapped_column(String(100))
    ft_home: Mapped[int | None] = mapped_column(SmallInteger)
    ft_away: Mapped[int | None] = mapped_column(SmallInteger)
    ht_home: Mapped[int | None] = mapped_column(SmallInteger)
    ht_away: Mapped[int | None] = mapped_column(SmallInteger)
    ft_result: Mapped[str | None] = mapped_column(String(1))  # H/D/A (skorlardan hesaplanır)
    ht_result: Mapped[str | None] = mapped_column(String(1))
    referee: Mapped[str | None] = mapped_column(String(80))
    ah_line: Mapped[float | None] = mapped_column(Float)  # Asya handikap çizgisi (kapanış değil)
    ah_line_closing: Mapped[float | None] = mapped_column(Float)
    import_run_id: Mapped[int] = mapped_column(ForeignKey("import_runs.id"))


class OddsSource(Base):
    """odds_history.source_id sözlüğü: bir kaynak sütunun anlamı."""

    __tablename__ = "odds_sources"
    __table_args__ = (
        UniqueConstraint("bookmaker", "market", "selection", "line_key", "odds_type", name="uq_odds_source"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    source_column: Mapped[str] = mapped_column(String(30))  # ilk görülen kaynak sütun adı, örn. "B365CH"
    bookmaker: Mapped[str] = mapped_column(String(20))  # B365, PS, Max, Avg ...
    bookmaker_name: Mapped[str] = mapped_column(String(60))
    market: Mapped[str] = mapped_column(String(10))  # 1X2 | OU | AH
    selection: Mapped[str] = mapped_column(String(10))  # 1,X,2 | over,under | home,away
    line: Mapped[float | None] = mapped_column(Float)  # OU için 2.5; AH için maça özgü (matches.ah_line)
    line_key: Mapped[str] = mapped_column(String(8), default="")  # benzersizlik için ("" = çizgi yok)
    odds_type: Mapped[str] = mapped_column(String(10))  # pre | closing | unspecified


class OddsHistory(Base):
    __tablename__ = "odds_history"
    __table_args__ = (
        UniqueConstraint("match_id", "source_id", "import_run_id", name="uq_odds_obs"),
        Index("ix_odds_match", "match_id"),
        Index("ix_odds_source", "source_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    source_id: Mapped[int] = mapped_column(ForeignKey("odds_sources.id"))
    odds: Mapped[float] = mapped_column(Float)
    # Kaynak dosyalar gözlem zamanını vermez; bilinmiyorsa NULL kalır (uydurulmaz).
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime)
    import_run_id: Mapped[int] = mapped_column(ForeignKey("import_runs.id"))


class TeamMatchStat(Base):
    __tablename__ = "team_match_stats"
    __table_args__ = (UniqueConstraint("match_id", "side", name="uq_stat_match_side"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    side: Mapped[str] = mapped_column(String(1))  # H | A
    shots: Mapped[int | None] = mapped_column(SmallInteger)
    shots_on_target: Mapped[int | None] = mapped_column(SmallInteger)
    fouls: Mapped[int | None] = mapped_column(SmallInteger)
    corners: Mapped[int | None] = mapped_column(SmallInteger)
    yellow_cards: Mapped[int | None] = mapped_column(SmallInteger)
    red_cards: Mapped[int | None] = mapped_column(SmallInteger)
    free_kicks_conceded: Mapped[int | None] = mapped_column(SmallInteger)
    xg: Mapped[float | None] = mapped_column(Float)


class TeamStrengthHistory(Base):
    __tablename__ = "team_strength_history"
    __table_args__ = (Index("ix_strength_team_date", "team_id", "as_of_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    as_of_date: Mapped[date] = mapped_column(Date)  # değer, bu tarihten ÖNCE bilinenlerle hesaplanır
    method: Mapped[str] = mapped_column(String(30))  # elo, dixon_coles ...
    rating: Mapped[float | None] = mapped_column(Float)
    attack: Mapped[float | None] = mapped_column(Float)
    defence: Mapped[float | None] = mapped_column(Float)
    form: Mapped[dict | None] = mapped_column(JSON)


class Prediction(Base):
    __tablename__ = "predictions"
    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id"), index=True)
    fixture_ref: Mapped[str | None] = mapped_column(String(120))  # arşivde olmayan güncel maç
    model_name: Mapped[str] = mapped_column(String(40))
    model_version: Mapped[str] = mapped_column(String(40))
    probabilities: Mapped[dict] = mapped_column(JSON)
    data_scope: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class BacktestRun(Base):
    __tablename__ = "backtest_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    strategy: Mapped[str] = mapped_column(String(60))
    train_period: Mapped[str | None] = mapped_column(String(40))
    validation_period: Mapped[str | None] = mapped_column(String(40))
    test_period: Mapped[str | None] = mapped_column(String(40))
    parameters: Mapped[dict | None] = mapped_column(JSON)
    results: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Coupon(Base):
    __tablename__ = "coupons"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile: Mapped[str] = mapped_column(String(20))
    selections: Mapped[list] = mapped_column(JSON)
    total_odds: Mapped[float] = mapped_column(Float)
    est_probability: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(12), default="open")  # open/won/lost/void
    is_virtual: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    settled_at: Mapped[datetime | None] = mapped_column(DateTime)
    notes: Mapped[dict | None] = mapped_column(JSON)


class DataQualityLog(Base):
    __tablename__ = "data_quality_logs"
    __table_args__ = (Index("ix_dq_run_type", "import_run_id", "issue_type"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    import_run_id: Mapped[int] = mapped_column(ForeignKey("import_runs.id", ondelete="CASCADE"))
    severity: Mapped[str] = mapped_column(String(8))  # info | warning | error
    issue_type: Mapped[str] = mapped_column(String(40))
    sheet: Mapped[str | None] = mapped_column(String(40))
    row_number: Mapped[int | None] = mapped_column(Integer)
    match_key: Mapped[str | None] = mapped_column(String(40))
    column_name: Mapped[str | None] = mapped_column(String(40))
    raw_value: Mapped[str | None] = mapped_column(String(120))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def _outcomes_table() -> Table:
    """Skor/istatistiklerden türetilen gerçekleşen pazar sonuçları (bkz. app/markets.py). NULL = girdi yok."""
    from app.markets import INT_COLUMNS, TEXT_COLUMNS

    cols = [Column("match_id", Integer, ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True)]
    cols += [Column(c, SmallInteger) for c in INT_COLUMNS] + [Column(c, String(8)) for c in TEXT_COLUMNS]
    return Table("match_outcomes", Base.metadata, *cols)


match_outcomes = _outcomes_table()


ODDS_VIEW_SQL = """
CREATE VIEW odds_history_view AS
SELECT h.id, h.match_id, s.bookmaker, s.bookmaker_name, s.market, s.selection, s.line,
       h.odds, s.odds_type, h.recorded_at, h.import_run_id, s.source_column
FROM odds_history h JOIN odds_sources s ON s.id = h.source_id
"""
