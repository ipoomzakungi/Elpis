from pathlib import Path

import polars as pl

from src.models.providers import (
    LocalDatasetValidationReport,
    ProviderCapability,
    ProviderDataType,
    ProviderDownloadRequest,
    ProviderInfo,
    ProviderSymbol,
)
from src.providers.base import validate_normalized_frame
from src.providers.errors import (
    LocalFileValidationError,
    ProviderValidationError,
    UnsupportedCapabilityError,
)


class LocalFileProvider:
    """Provider for trusted local CSV and Parquet research datasets."""

    name = "local_file"
    display_name = "Local File"
    supported_timeframes = ["15m", "1h", "1d"]
    required_ohlcv_columns = ["timestamp", "open", "high", "low", "close", "volume"]

    def get_provider_info(self) -> ProviderInfo:
        return ProviderInfo(
            provider=self.name,
            display_name=self.display_name,
            supports_ohlcv=True,
            supports_open_interest=True,
            supports_funding_rate=True,
            requires_auth=False,
            supported_timeframes=self.supported_timeframes,
            default_symbol=None,
            limitations=["Capabilities depend on validated CSV or Parquet columns"],
            capabilities=[
                ProviderCapability(data_type=ProviderDataType.OHLCV, supported=True),
                ProviderCapability(data_type=ProviderDataType.OPEN_INTEREST, supported=True),
                ProviderCapability(data_type=ProviderDataType.FUNDING_RATE, supported=True),
            ],
        )

    def get_supported_symbols(self) -> list[ProviderSymbol]:
        return [
            ProviderSymbol(
                symbol="LOCAL",
                display_name="Validated local dataset",
                asset_class="local_dataset",
                supports_ohlcv=True,
                supports_open_interest=True,
                supports_funding_rate=True,
                notes=["Symbol is supplied by each local-file import request"],
            )
        ]

    def get_supported_timeframes(self) -> list[str]:
        return self.supported_timeframes.copy()

    def validate_symbol(self, symbol: str) -> str:
        normalized = symbol.strip().upper()
        if not normalized:
            raise ProviderValidationError("Local file imports require a symbol")
        return normalized

    def validate_timeframe(self, timeframe: str) -> str:
        normalized = timeframe.strip().lower()
        if normalized not in self.supported_timeframes:
            raise ProviderValidationError(
                f"Timeframe '{timeframe}' is not supported by provider '{self.name}'"
            )
        return normalized

    async def fetch_ohlcv(self, request: ProviderDownloadRequest) -> pl.DataFrame:
        symbol = self.validate_symbol(request.symbol or "")
        timeframe = self.validate_timeframe(request.timeframe)
        frame = self._read_request_file(request)
        report = self.validate_frame(frame, str(request.local_file_path))
        if not report.is_valid:
            raise self._validation_error(report)
        return self._normalize_ohlcv(frame, symbol=symbol, timeframe=timeframe)

    async def fetch_open_interest(self, request: ProviderDownloadRequest) -> pl.DataFrame:
        symbol = self.validate_symbol(request.symbol or "")
        timeframe = self.validate_timeframe(request.timeframe)
        frame = self._read_request_file(request)
        report = self.validate_frame(frame, str(request.local_file_path))
        if not report.is_valid:
            raise self._validation_error(report)
        if ProviderDataType.OPEN_INTEREST not in report.detected_capabilities:
            raise UnsupportedCapabilityError(
                self.name,
                ProviderDataType.OPEN_INTEREST.value,
                "Local file does not contain a valid open_interest column",
            )
        return self._normalize_open_interest(frame, symbol=symbol, timeframe=timeframe)

    async def fetch_funding_rate(self, request: ProviderDownloadRequest) -> pl.DataFrame:
        symbol = self.validate_symbol(request.symbol or "")
        timeframe = self.validate_timeframe(request.timeframe)
        frame = self._read_request_file(request)
        report = self.validate_frame(frame, str(request.local_file_path))
        if not report.is_valid:
            raise self._validation_error(report)
        if ProviderDataType.FUNDING_RATE not in report.detected_capabilities:
            raise UnsupportedCapabilityError(
                self.name,
                ProviderDataType.FUNDING_RATE.value,
                "Local file does not contain a valid funding_rate column",
            )
        return self._normalize_funding_rate(frame, symbol=symbol, timeframe=timeframe)

    def validate_file(self, file_path: str | Path) -> LocalDatasetValidationReport:
        path = Path(file_path)
        try:
            frame = self._read_file(path)
        except LocalFileValidationError as exc:
            return LocalDatasetValidationReport(
                file_path=str(path),
                is_valid=False,
                timestamp_parseable=False,
                errors=[exc.message],
            )
        return self.validate_frame(frame, str(path))

    def validate_frame(self, frame: pl.DataFrame, file_path: str) -> LocalDatasetValidationReport:
        missing_columns = [
            column for column in self.required_ohlcv_columns if column not in frame.columns
        ]
        errors = []
        if missing_columns:
            errors.append(f"Missing required columns: {', '.join(missing_columns)}")

        timestamp_column = "timestamp" if "timestamp" in frame.columns else None
        timestamp_parseable = False
        duplicate_timestamps = 0
        parsed = frame
        if timestamp_column:
            parsed = frame.with_columns(
                pl.col(timestamp_column).cast(pl.Datetime, strict=False).alias("_parsed_timestamp")
            )
            timestamp_parseable = bool(
                parsed.select(pl.col("_parsed_timestamp").is_not_null().all()).item()
            )
            if not timestamp_parseable:
                errors.append("Timestamp values are not fully parseable")
            duplicate_timestamps = int(
                parsed.filter(pl.col("_parsed_timestamp").is_duplicated()).height
            )
            if duplicate_timestamps:
                errors.append(f"Duplicate timestamps found: {duplicate_timestamps}")

        missing_required_values = self._missing_required_values(frame)
        for column, count in missing_required_values.items():
            if count > 0:
                errors.append(f"Missing required values in {column}: {count}")

        detected_capabilities = []
        if not errors:
            detected_capabilities.append(ProviderDataType.OHLCV)
        if self._valid_optional_column(frame, "open_interest"):
            detected_capabilities.append(ProviderDataType.OPEN_INTEREST)
        if self._valid_optional_column(frame, "funding_rate"):
            detected_capabilities.append(ProviderDataType.FUNDING_RATE)

        return LocalDatasetValidationReport(
            file_path=file_path,
            is_valid=not errors,
            detected_capabilities=detected_capabilities,
            required_columns_missing=missing_columns,
            timestamp_column=timestamp_column,
            timestamp_parseable=timestamp_parseable,
            duplicate_timestamps=duplicate_timestamps,
            missing_required_values=missing_required_values,
            errors=errors,
            warnings=[],
        )

    def _read_request_file(self, request: ProviderDownloadRequest) -> pl.DataFrame:
        if request.local_file_path is None:
            raise ProviderValidationError("local_file_path is required for local_file provider")
        return self._read_file(request.local_file_path)

    def _read_file(self, file_path: str | Path) -> pl.DataFrame:
        path = Path(file_path)
        if not path.exists():
            raise LocalFileValidationError(
                "Local file is not valid OHLCV research data",
                details=[{"field": "local_file_path", "message": f"File not found: {path}"}],
            )
        if path.suffix.lower() == ".csv":
            return pl.read_csv(path)
        if path.suffix.lower() == ".parquet":
            return pl.read_parquet(path)
        raise LocalFileValidationError(
            "Local file is not valid OHLCV research data",
            details=[
                {"field": "local_file_path", "message": "Only CSV and Parquet files are supported"}
            ],
        )

    def _missing_required_values(self, frame: pl.DataFrame) -> dict[str, int]:
        return {
            column: int(frame[column].null_count())
            for column in self.required_ohlcv_columns
            if column in frame.columns
        }

    def _valid_optional_column(self, frame: pl.DataFrame, column: str) -> bool:
        return column in frame.columns and int(frame[column].null_count()) == 0

    def _normalize_ohlcv(self, frame: pl.DataFrame, symbol: str, timeframe: str) -> pl.DataFrame:
        normalized = self._with_common_columns(
            frame, symbol=symbol, timeframe=timeframe
        ).with_columns(
            [
                self._optional_float(frame, "quote_volume"),
                self._optional_int(frame, "trades"),
                self._optional_float(frame, "taker_buy_volume"),
            ]
        )
        validate_normalized_frame(normalized, ProviderDataType.OHLCV.value)
        return normalized.select(
            [
                "timestamp",
                "provider",
                "symbol",
                "timeframe",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "quote_volume",
                "trades",
                "taker_buy_volume",
                "source",
            ]
        )

    def _normalize_open_interest(
        self,
        frame: pl.DataFrame,
        symbol: str,
        timeframe: str,
    ) -> pl.DataFrame:
        normalized = self._with_common_columns(
            frame, symbol=symbol, timeframe=timeframe
        ).with_columns(
            [
                pl.col("open_interest").cast(pl.Float64),
                self._optional_float(frame, "open_interest_value"),
            ]
        )
        validate_normalized_frame(normalized, ProviderDataType.OPEN_INTEREST.value)
        return normalized.select(
            [
                "timestamp",
                "provider",
                "symbol",
                "timeframe",
                "open_interest",
                "open_interest_value",
                "source",
            ]
        )

    def _normalize_funding_rate(
        self,
        frame: pl.DataFrame,
        symbol: str,
        timeframe: str,
    ) -> pl.DataFrame:
        normalized = self._with_common_columns(
            frame, symbol=symbol, timeframe=timeframe
        ).with_columns(
            [
                pl.col("funding_rate").cast(pl.Float64),
                self._optional_float(frame, "mark_price"),
            ]
        )
        validate_normalized_frame(normalized, ProviderDataType.FUNDING_RATE.value)
        return normalized.select(
            [
                "timestamp",
                "provider",
                "symbol",
                "timeframe",
                "funding_rate",
                "mark_price",
                "source",
            ]
        )

    def _with_common_columns(
        self, frame: pl.DataFrame, symbol: str, timeframe: str
    ) -> pl.DataFrame:
        return (
            frame.with_columns(
                [
                    pl.col("timestamp").cast(pl.Datetime, strict=False).alias("timestamp"),
                    pl.lit(self.name).alias("provider"),
                    pl.lit(symbol).alias("symbol"),
                    pl.lit(timeframe).alias("timeframe"),
                    pl.lit("local_file").alias("source"),
                    pl.col("open").cast(pl.Float64),
                    pl.col("high").cast(pl.Float64),
                    pl.col("low").cast(pl.Float64),
                    pl.col("close").cast(pl.Float64),
                    pl.col("volume").cast(pl.Float64),
                ]
            )
            .drop_nulls(subset=self.required_ohlcv_columns)
            .unique(subset=["timestamp"])
            .sort("timestamp")
        )

    def _optional_float(self, frame: pl.DataFrame, column: str) -> pl.Expr:
        if column in frame.columns:
            return pl.col(column).cast(pl.Float64)
        return pl.lit(None).cast(pl.Float64).alias(column)

    def _optional_int(self, frame: pl.DataFrame, column: str) -> pl.Expr:
        if column in frame.columns:
            return pl.col(column).cast(pl.Int64)
        return pl.lit(None).cast(pl.Int64).alias(column)

    def _validation_error(self, report: LocalDatasetValidationReport) -> LocalFileValidationError:
        details = []
        for column in report.required_columns_missing:
            details.append({"field": column, "message": "Missing required column"})
        if not report.timestamp_parseable:
            details.append({"field": "timestamp", "message": "Timestamp values are not parseable"})
        if report.duplicate_timestamps:
            details.append(
                {
                    "field": "timestamp",
                    "message": f"Duplicate timestamps found: {report.duplicate_timestamps}",
                }
            )
        for column, count in report.missing_required_values.items():
            if count:
                details.append({"field": column, "message": f"Missing required values: {count}"})
        return LocalFileValidationError(
            "Local file is not valid OHLCV research data",
            details=details,
        )
