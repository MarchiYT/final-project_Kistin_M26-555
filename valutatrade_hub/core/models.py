"""Пользователь, кошелёк и портфель."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import InsufficientFundsError
from valutatrade_hub.core.utils import cached_rate, parse_time, validate_number


class User:
    """Пользователь с солёным хешем пароля."""

    def __init__(self, user_id, username, hashed_password, salt, registration_date):
        if type(user_id) is not int or user_id <= 0:
            raise ValueError("user_id должен быть положительным целым числом")
        self._user_id = user_id
        self.username = username
        if (
            not isinstance(hashed_password, str)
            or not isinstance(salt, str)
            or not salt
        ):
            raise ValueError("Некорректные данные пароля")
        if len(hashed_password) != 64:
            raise ValueError("Некорректный хеш пароля")
        self._hashed_password = hashed_password
        self._salt = salt
        self._registration_date = (
            parse_time(registration_date)
            if isinstance(registration_date, str)
            else registration_date
        )
        if not isinstance(self._registration_date, datetime):
            raise ValueError("Некорректная дата регистрации")

    @classmethod
    def create(cls, user_id, username, password):
        """Создать пользователя с новой случайной солью."""
        cls._validate_password(password)
        salt = secrets.token_hex(16)
        hashed = hashlib.sha256((password + salt).encode()).hexdigest()
        return cls(user_id, username, hashed, salt, datetime.now(UTC))

    @staticmethod
    def _validate_password(password):
        if not isinstance(password, str) or len(password) < 4:
            raise ValueError("Пароль должен быть не короче 4 символов")

    @property
    def user_id(self):
        return self._user_id

    @property
    def username(self):
        return self._username

    @username.setter
    def username(self, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Имя пользователя не может быть пустым")
        self._username = value.strip()

    @property
    def hashed_password(self):
        return self._hashed_password

    @property
    def salt(self):
        return self._salt

    @property
    def registration_date(self):
        return self._registration_date

    def get_user_info(self):
        """Вернуть данные пользователя без хеша и соли."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "registration_date": self.registration_date.isoformat(),
        }

    def change_password(self, new_password):
        """Проверить длину и сохранить новый хеш с новой солью."""
        self._validate_password(new_password)
        self._salt = secrets.token_hex(16)
        self._hashed_password = hashlib.sha256(
            (new_password + self.salt).encode()
        ).hexdigest()

    def verify_password(self, password):
        """Сравнить хеш введённого пароля с сохранённым."""
        if not isinstance(password, str):
            return False
        hashed = hashlib.sha256((password + self.salt).encode()).hexdigest()
        return hmac.compare_digest(hashed, self.hashed_password)

    def to_dict(self):
        """Подготовить запись для users.json."""
        return {
            **self.get_user_info(),
            "hashed_password": self.hashed_password,
            "salt": self.salt,
        }


class Wallet:
    """Баланс одной валюты."""

    def __init__(self, currency_code, balance=0.0):
        self.currency_code = get_currency(currency_code).code
        self.balance = balance

    @property
    def balance(self):
        return self._balance

    @balance.setter
    def balance(self, value):
        self._balance = validate_number(value, "balance", allow_zero=True)

    def deposit(self, amount):
        """Пополнить кошелёк на положительную сумму."""
        amount = validate_number(amount)
        self.balance += amount

    def withdraw(self, amount):
        """Снять сумму, если хватает средств."""
        amount = validate_number(amount)
        if amount > self.balance:
            raise InsufficientFundsError(self.balance, amount, self.currency_code)
        self.balance -= amount

    def get_balance_info(self):
        """Вернуть читаемый остаток валюты."""
        return f"{self.currency_code}: {self.balance:.8f}"


class Portfolio:
    """Кошельки одного пользователя."""

    def __init__(self, user, wallets=None):
        if not isinstance(user, User):
            raise ValueError("Портфель должен принадлежать пользователю")
        self._user = user
        self._user_id = user.user_id
        self._wallets = dict(wallets or {})
        for code, wallet in self._wallets.items():
            if not isinstance(wallet, Wallet) or code != wallet.currency_code:
                raise ValueError("Некорректный словарь кошельков")

    @property
    def user(self):
        return self._user

    @property
    def wallets(self):
        return self._wallets.copy()

    def add_currency(self, currency_code):
        """Создать кошелёк, если этой валюты ещё нет."""
        code = get_currency(currency_code).code
        if code not in self._wallets:
            self._wallets[code] = Wallet(code)
        return self._wallets[code]

    def get_wallet(self, currency_code):
        """Вернуть кошелёк по известному коду валюты."""
        get_currency(currency_code)
        if currency_code not in self._wallets:
            raise ValueError(
                f"У вас нет кошелька '{currency_code}'. "
                "Он создаётся автоматически при первой покупке."
            )
        return self._wallets[currency_code]

    def get_total_value(self, base_currency="USD", exchange_rates=None):
        """Посчитать стоимость портфеля по переданному или локальному кэшу."""
        get_currency(base_currency)
        if exchange_rates is None:
            from valutatrade_hub.infra.database import DatabaseManager

            exchange_rates = DatabaseManager().read("rates")["pairs"]
        total = 0.0
        for code, wallet in self._wallets.items():
            if wallet.balance:
                entry = cached_rate(exchange_rates, code, base_currency)
                total += wallet.balance * entry["rate"]
        return validate_number(total, "total", allow_zero=True)

    def to_dict(self):
        """Подготовить запись для portfolios.json."""
        return {
            "user_id": self._user_id,
            "wallets": {
                code: {"balance": wallet.balance}
                for code, wallet in self._wallets.items()
            },
        }
