"""Ошибки операций с кошельками и курсами."""


class InsufficientFundsError(Exception):
    """На кошельке меньше средств, чем нужно для списания."""

    def __init__(self, available, required, code):
        self.available = available
        self.required = required
        self.code = code
        super().__init__(
            f"Недостаточно средств: доступно {available:g} {code}, "
            f"требуется {required:g} {code}"
        )


class CurrencyNotFoundError(Exception):
    """Код отсутствует в реестре валют."""

    def __init__(self, code):
        super().__init__(f"Неизвестная валюта '{code}'")


class ApiRequestError(Exception):
    """Источник не вернул пригодные для работы курсы."""

    def __init__(self, reason):
        super().__init__(f"Ошибка при обращении к внешнему API: {reason}")
