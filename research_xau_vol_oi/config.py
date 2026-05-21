"""Configuration and shared enums for the XAU Vol-OI research pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class Signal(StrEnum):
    """Deterministic research labels, not order instructions."""

    NO_TRADE = "NO_TRADE"
    NO_TRADE_MIDDLE = "NO_TRADE_MIDDLE"
    WATCH_WALL = "WATCH_WALL"
    FADE_WALL_SHORT = "FADE_WALL_SHORT"
    FADE_WALL_LONG = "FADE_WALL_LONG"
    BREAK_WALL_LONG = "BREAK_WALL_LONG"
    BREAK_WALL_SHORT = "BREAK_WALL_SHORT"
    PIN_RISK = "PIN_RISK"
    SQUEEZE_RISK = "SQUEEZE_RISK"
    RANDOM_BASELINE = "RANDOM_BASELINE"
    SD_ONLY_BASELINE = "SD_ONLY_BASELINE"


class WallSide(StrEnum):
    """Wall orientation relative to the current reference price."""

    SUPPORT = "support"
    RESISTANCE = "resistance"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class VolRegime(StrEnum):
    """Simple IV/RV/VRP regime labels."""

    UNKNOWN = "UNKNOWN"
    IV_PREMIUM = "IV_PREMIUM"
    RV_PREMIUM = "RV_PREMIUM"
    BALANCED = "BALANCED"
    STRESS = "STRESS"


DIRECTIONAL_SIGNALS = {
    Signal.FADE_WALL_LONG,
    Signal.FADE_WALL_SHORT,
    Signal.BREAK_WALL_LONG,
    Signal.BREAK_WALL_SHORT,
}


@dataclass(frozen=True)
class ColumnAliases:
    """Column names accepted by the standardizers."""

    timestamp: tuple[str, ...] = ("timestamp", "datetime", "date", "time")
    symbol: tuple[str, ...] = ("symbol", "ticker", "futures_symbol")
    open: tuple[str, ...] = ("open", "Open")
    high: tuple[str, ...] = ("high", "High")
    low: tuple[str, ...] = ("low", "Low")
    close: tuple[str, ...] = ("close", "Close", "adj_close", "last", "price")
    volume: tuple[str, ...] = ("volume", "Volume", "intraday_volume")
    expiry: tuple[str, ...] = ("expiry", "expiration", "expiration_date")
    dte: tuple[str, ...] = ("dte", "days_to_expiry", "DTE")
    strike: tuple[str, ...] = ("strike", "option_strike", "cme_option_strike")
    option_type: tuple[str, ...] = ("option_type", "put_call", "type", "side")
    open_interest: tuple[str, ...] = (
        "open_interest",
        "total_oi",
        "oi",
        "Open Interest",
    )
    call_oi: tuple[str, ...] = ("call_oi", "calls_oi", "call_open_interest")
    put_oi: tuple[str, ...] = ("put_oi", "puts_oi", "put_open_interest")
    oi_change: tuple[str, ...] = ("oi_change", "open_interest_change", "change_oi")
    iv: tuple[str, ...] = (
        "iv",
        "implied_volatility",
        "annualized_iv_percent",
        "implied_volatility_percent",
    )
    futures_price: tuple[str, ...] = (
        "gold_futures_price",
        "underlying_futures_price",
        "futures_price",
    )
    spot_price: tuple[str, ...] = (
        "xauusd_spot_price",
        "spot_price",
        "xauusd",
        "xau_price",
    )


@dataclass(frozen=True)
class ResearchConfig:
    """Research thresholds and output paths.

    Defaults are intentionally conservative and transparent. They should be
    treated as formation-period parameters, not optimized trading constants.
    """

    output_dir: Path = Path("outputs")
    chart_dir_name: str = "charts"
    data_roots: tuple[Path, ...] = (
        Path("data"),
        Path("backend/data"),
        Path(".local/research"),
    )
    accepted_file_extensions: tuple[str, ...] = (
        ".csv",
        ".parquet",
        ".xlsx",
        ".xls",
        ".txt",
        ".md",
        ".srt",
        ".json",
        ".jsonl",
    )
    exclude_dir_names: tuple[str, ...] = (
        ".git",
        ".venv",
        "venv",
        "node_modules",
        ".next",
        "__pycache__",
        ".pytest_cache",
    )
    aliases: ColumnAliases = field(default_factory=ColumnAliases)
    annual_trading_days: int = 252
    session_open_hour_utc: int = 4
    session_close_hour_utc: int = 21
    min_wall_score: float = 0.05
    strong_wall_score: float = 0.20
    pin_wall_score: float = 0.25
    near_expiry_days: int = 7
    proximity_points: float = 8.0
    proximity_sd_fraction: float = 0.20
    sd_boundary_fraction: float = 0.15
    acceptance_buffer_points: float = 2.0
    breakout_requires_vol_expansion: bool = False
    vol_expansion_multiple: float = 1.10
    low_oi_gap_points: float = 20.0
    backtest_horizon_bars: int = 8
    walk_forward_train_bars: int = 100
    walk_forward_test_bars: int = 50
    random_seed: int = 7
