"""Общий интерфейс фиатных и криптовалют."""

from abc import ABC, abstractmethod

from valutatrade_hub.core.exceptions import CurrencyNotFoundError
from valutatrade_hub.core.utils import validate_code, validate_number


class Currency(ABC):
    """Валюта с названием и кодом."""

    def __init__(self, name, code):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Название валюты не может быть пустым")
        self.name = name.strip()
        self.code = validate_code(code)

    @abstractmethod
    def get_display_info(self):
        """Вернуть описание валюты для интерфейса."""


class FiatCurrency(Currency):
    """Фиатная валюта со страной или зоной эмиссии."""

    def __init__(self, name, code, issuing_country):
        super().__init__(name, code)
        if not isinstance(issuing_country, str) or not issuing_country.strip():
            raise ValueError("Нужно указать страну или зону эмиссии")
        self.issuing_country = issuing_country

    def get_display_info(self):
        """Вернуть код, название и эмитента."""
        return f"[FIAT] {self.code} — {self.name} (Issuing: {self.issuing_country})"


class CryptoCurrency(Currency):
    """Криптовалюта с алгоритмом и капитализацией."""

    def __init__(self, name, code, algorithm, market_cap=0.0):
        super().__init__(name, code)
        if not isinstance(algorithm, str) or not algorithm.strip():
            raise ValueError("Нужно указать алгоритм")
        self.algorithm = algorithm
        self.market_cap = validate_number(market_cap, "market_cap", allow_zero=True)

    def get_display_info(self):
        """Вернуть код, алгоритм и последнюю известную капитализацию."""
        return (
            f"[CRYPTO] {self.code} — {self.name} "
            f"(Algo: {self.algorithm}, MCAP: {self.market_cap:.2e})"
        )


CURRENCIES = {
    "USD": FiatCurrency("US Dollar", "USD", "United States"),
    "EUR": FiatCurrency("Euro", "EUR", "Eurozone"),
    "GBP": FiatCurrency("Pound Sterling", "GBP", "United Kingdom"),
    "RUB": FiatCurrency("Russian Ruble", "RUB", "Russia"),
    "BTC": CryptoCurrency("Bitcoin", "BTC", "SHA-256"),
    "ETH": CryptoCurrency("Ethereum", "ETH", "Proof of Stake"),
    "SOL": CryptoCurrency("Solana", "SOL", "Proof of History"),
}


def get_currency(code):
    """Найти валюту в реестре или сообщить о неизвестном коде."""
    validate_code(code)
    if code not in CURRENCIES:
        raise CurrencyNotFoundError(code)
    return CURRENCIES[code]
