from abc import ABC, abstractmethod

import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.core.utils import utc_now, validate_number
from valutatrade_hub.parser_service.config import ParserConfig


class BaseApiClient(ABC):
    source = ""

    def __init__(self, config=None):
        self.config = config or ParserConfig()
        self.updated_at = None

    def _request(self, url, params=None, headers=None):
        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=self.config.REQUEST_TIMEOUT,
            )
        except requests.RequestException as error:
            raise ApiRequestError(f"{self.source}: ошибка сети") from error
        try:
            if response.status_code != 200:
                raise ApiRequestError(f"{self.source}: HTTP {response.status_code}")
            try:
                data = response.json()
            except ValueError as error:
                raise ApiRequestError(f"{self.source}: неверный JSON") from error
            if not isinstance(data, dict):
                raise ApiRequestError(f"{self.source}: неверный формат ответа")
            self.updated_at = utc_now()
            return data
        finally:
            response.close()

    @abstractmethod
    def fetch_rates(self):
        """Получить словарь курсов к USD."""


class CoinGeckoClient(BaseApiClient):
    source = "CoinGecko"

    def fetch_rates(self):
        headers = {}
        if self.config.COINGECKO_API_KEY:
            headers["x-cg-demo-api-key"] = self.config.COINGECKO_API_KEY
        data = self._request(
            self.config.COINGECKO_URL,
            params={
                "ids": ",".join(
                    self.config.CRYPTO_ID_MAP[code]
                    for code in self.config.CRYPTO_CURRENCIES
                ),
                "vs_currencies": "usd",
            },
            headers=headers,
        )
        try:
            return {
                code + "_USD": validate_number(
                    data[self.config.CRYPTO_ID_MAP[code]]["usd"], "rate"
                )
                for code in self.config.CRYPTO_CURRENCIES
            }
        except (KeyError, TypeError, ValueError) as error:
            raise ApiRequestError("CoinGecko: нет корректного курса") from error


class ExchangeRateApiClient(BaseApiClient):
    source = "ExchangeRate-API"

    def fetch_rates(self):
        if self.config.EXCHANGERATE_API_KEY:
            url = (
                f"{self.config.EXCHANGERATE_API_URL}/"
                f"{self.config.EXCHANGERATE_API_KEY}/latest/USD"
            )
        else:
            url = self.config.EXCHANGERATE_OPEN_URL + "/USD"
        data = self._request(url)
        if data.get("result") != "success" or data.get("base_code") != "USD":
            raise ApiRequestError("ExchangeRate-API: не удалось получить курсы USD")
        values = data.get("conversion_rates", data.get("rates"))
        try:
            return {
                code + "_USD": validate_number(
                    1 / validate_number(values[code], "rate"), "rate"
                )
                for code in self.config.FIAT_CURRENCIES
            }
        except (KeyError, TypeError, ValueError) as error:
            raise ApiRequestError("ExchangeRate-API: нет корректного курса") from error
