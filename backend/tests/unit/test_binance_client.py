import httpx
import pytest

from src.services.binance_client import BinanceClient


def kline_row(timestamp: int) -> list:
    return [
        timestamp,
        "100.0",
        "102.0",
        "99.0",
        "101.0",
        "10.0",
        timestamp + 899999,
        "1000.0",
        20,
        "5.0",
        "500.0",
        "0",
    ]


@pytest.mark.asyncio()
async def test_get_klines_sends_expected_request():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=[kline_row(1000)])

    client = BinanceClient()
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    data = await client.get_klines(symbol="BTCUSDT", interval="15m", start_time=1000, end_time=2000)
    await client.close()

    assert seen["path"] == "/fapi/v1/klines"
    assert seen["params"]["symbol"] == "BTCUSDT"
    assert seen["params"]["interval"] == "15m"
    assert data == [kline_row(1000)]


@pytest.mark.asyncio()
async def test_download_ohlcv_converts_and_deduplicates_rows():
    responses = iter([[kline_row(1000), kline_row(1000)], []])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(responses))

    client = BinanceClient()
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    data = await client.download_ohlcv(days=1)
    await client.close()

    assert len(data) == 1
    assert data.row(0, named=True)["open"] == pytest.approx(100.0)
    assert data.row(0, named=True)["trades"] == 20


@pytest.mark.asyncio()
async def test_download_open_interest_converts_payload():
    responses = iter(
        [
            [
                {
                    "symbol": "BTCUSDT",
                    "sumOpenInterest": "1000.0",
                    "sumOpenInterestValue": "100000.0",
                    "timestamp": 1000,
                }
            ],
            [],
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(responses))

    client = BinanceClient()
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    data = await client.download_open_interest(days=1)
    await client.close()

    assert len(data) == 1
    assert data.row(0, named=True)["open_interest"] == pytest.approx(1000.0)


@pytest.mark.asyncio()
async def test_binance_http_errors_are_propagated():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, request=request, json={"msg": "rate limit"})

    client = BinanceClient()
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    with pytest.raises(httpx.HTTPStatusError):
        await client.get_funding_rate()

    await client.close()
