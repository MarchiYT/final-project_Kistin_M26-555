"""Параметры внешних источников курсов."""

import os


class ParserConfig:
    """Адреса API, валюты, ключи из окружения и пути к данным."""

    BASE_CURRENCY = "USD"
    FIAT_CURRENCIES = ("EUR", "GBP", "RUB")
    CRYPTO_CURRENCIES = ("BTC", "ETH", "SOL")
    CRYPTO_ID_MAP = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana"}
    COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
    EXCHANGERATE_API_URL = "https://v6.exchangerate-api.com/v6"
    EXCHANGERATE_OPEN_URL = "https://open.er-api.com/v6/latest"
    REQUEST_TIMEOUT = 10

    def __init__(self):
        self.EXCHANGERATE_API_KEY = os.getenv("EXCHANGERATE_API_KEY", "")
        self.COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")
