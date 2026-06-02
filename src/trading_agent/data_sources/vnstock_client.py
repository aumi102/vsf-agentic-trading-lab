from __future__ import annotations

import contextlib
import importlib
import io
from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd


@dataclass
class FetchResult:
    dataset: str
    status: str
    data: pd.DataFrame | None = None
    symbol: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "success" and self.data is not None


class VnstockClient:
    """Small boundary around vnstock so library-specific calls stay isolated."""

    def __init__(self, source: str = "VCI") -> None:
        self.source = source

    def get_listing_all_symbols(self) -> FetchResult:
        return self._fetch("listing_all_symbols", self._listing_all_symbols)

    def get_listing_symbols_by_exchange(self) -> FetchResult:
        return self._fetch("listing_symbols_by_exchange", self._listing_symbols_by_exchange)

    def get_ohlcv(self, symbol: str, start: str, end: str) -> FetchResult:
        return self._fetch("ohlcv", lambda: self._ohlcv(symbol, start, end), symbol=symbol)

    def get_company_events(self, symbol: str) -> FetchResult:
        return self._fetch("company_events", lambda: self._company_events(symbol), symbol=symbol)

    def _fetch(self, dataset: str, call: Callable[[], Any], symbol: str | None = None) -> FetchResult:
        try:
            with self._suppress_library_output():
                data = self._to_dataframe(call())
            return FetchResult(dataset=dataset, status="success", data=data, symbol=symbol)
        except ModuleNotFoundError as exc:
            if exc.name == "vnstock":
                return FetchResult(
                    dataset=dataset,
                    status="failure",
                    symbol=symbol,
                    error="Missing dependency: install vnstock, for example `pip install vnstock`.",
                )
            return FetchResult(dataset=dataset, status="failure", symbol=symbol, error=str(exc))
        except ImportError as exc:
            return FetchResult(
                dataset=dataset,
                status="failure",
                symbol=symbol,
                error=f"Could not import vnstock dependency: {exc}",
            )
        except Exception as exc:  # pragma: no cover - exact vnstock errors vary by version/network
            return FetchResult(dataset=dataset, status="failure", symbol=symbol, error=str(exc))

    def _stock(self, symbol: str = "VCI") -> Any:
        Vnstock = self._import_vnstock_attr("Vnstock")

        return Vnstock().stock(symbol=symbol, source=self.source)

    def _listing_all_symbols(self) -> Any:
        try:
            stock = self._stock()
            listing = getattr(stock, "listing", None)
            if listing is not None and hasattr(listing, "all_symbols"):
                return listing.all_symbols()
        except Exception:
            pass

        Vnstock = self._import_vnstock_attr("Vnstock")

        root = Vnstock()
        listing = getattr(root, "listing", None)
        if listing is not None and hasattr(listing, "all_symbols"):
            return listing.all_symbols()

        try:
            listing_companies = self._import_vnstock_attr("listing_companies")

            return listing_companies()
        except Exception as exc:
            raise RuntimeError("No supported vnstock listing_all_symbols call pattern worked.") from exc

    def _listing_symbols_by_exchange(self) -> Any:
        stock = self._stock()
        listing = getattr(stock, "listing", None)
        if listing is not None and hasattr(listing, "symbols_by_exchange"):
            return listing.symbols_by_exchange()

        try:
            Vnstock = self._import_vnstock_attr("Vnstock")

            root_listing = getattr(Vnstock(), "listing", None)
            if root_listing is not None and hasattr(root_listing, "symbols_by_exchange"):
                return root_listing.symbols_by_exchange()
        except Exception:
            pass

        raise RuntimeError("No supported vnstock listing_symbols_by_exchange call pattern worked.")

    def _ohlcv(self, symbol: str, start: str, end: str) -> Any:
        try:
            stock = self._stock(symbol)
            quote = getattr(stock, "quote", None)
            if quote is not None and hasattr(quote, "history"):
                return quote.history(start=start, end=end, interval="1D")
        except Exception:
            pass

        try:
            stock_historical_data = self._import_vnstock_attr("stock_historical_data")

            return stock_historical_data(symbol=symbol, start_date=start, end_date=end, resolution="1D", type="stock", beautify=True)
        except Exception as exc:
            raise RuntimeError(f"No supported vnstock OHLCV call pattern worked for {symbol}.") from exc

    def _company_events(self, symbol: str) -> Any:
        stock = self._stock(symbol)
        company = getattr(stock, "company", None)
        if company is not None and hasattr(company, "events"):
            return company.events()

        try:
            company_events = self._import_vnstock_attr("company_events")

            return company_events(symbol)
        except Exception as exc:
            raise RuntimeError(f"No supported vnstock company_events call pattern worked for {symbol}.") from exc

    @staticmethod
    @contextlib.contextmanager
    def _suppress_library_output() -> Any:
        """Prevent vnstock console banners from breaking Windows cp1252 terminals."""
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            yield

    @staticmethod
    def _import_vnstock_attr(name: str) -> Any:
        module = importlib.import_module("vnstock")
        return getattr(module, name)

    @staticmethod
    def _to_dataframe(data: Any) -> pd.DataFrame:
        if isinstance(data, pd.DataFrame):
            return data.copy()
        if isinstance(data, pd.Series):
            return data.to_frame().reset_index()
        if isinstance(data, list):
            if not data:
                return pd.DataFrame()
            if all(isinstance(item, dict) for item in data):
                return pd.DataFrame(data)
            return pd.DataFrame({"symbol": data})
        if isinstance(data, dict):
            return pd.DataFrame([data])
        return pd.DataFrame(data)
