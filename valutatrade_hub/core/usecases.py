"""Операции с пользователями, портфелями и курсами."""

from valutatrade_hub.core.currencies import CURRENCIES, CryptoCurrency, get_currency
from valutatrade_hub.core.models import Portfolio, User, Wallet
from valutatrade_hub.core.utils import cached_rate, is_fresh, validate_number
from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.updater import update_rates


class TradingService:
    def __init__(self, database=None):
        self.database = database or DatabaseManager()
        self.settings = SettingsLoader()
        self.current_user = None

    def register(self, username, password):
        if not isinstance(username, str) or not username.strip():
            raise ValueError("Имя пользователя не может быть пустым")
        username = username.strip()
        users = self.database.read("users")
        portfolios = self.database.read("portfolios")
        if any(user["username"] == username for user in users):
            raise ValueError(f"Имя пользователя '{username}' уже занято")
        user_id = max((user["user_id"] for user in users), default=0) + 1
        user = User.create(user_id, username, password)
        self.database.write("portfolios", portfolios + [Portfolio(user).to_dict()])
        try:
            self.database.write("users", users + [user.to_dict()])
        except (OSError, ValueError):
            self.database.write("portfolios", portfolios)
            raise
        return user.get_user_info()

    def login(self, username, password):
        if not isinstance(username, str) or not username.strip():
            raise ValueError("Имя пользователя не может быть пустым")
        for record in self.database.read("users"):
            if record["username"] == username.strip():
                user = User(**record)
                if not user.verify_password(password):
                    raise ValueError("Неверный пароль")
                self.current_user = user
                return user.get_user_info()
        raise ValueError(f"Пользователь '{username}' не найден")

    def logout(self):
        self.current_user = None

    def _require_user(self):
        if self.current_user is None:
            raise ValueError("Сначала выполните login")
        return self.current_user

    def _load_portfolio(self, records):
        user = self._require_user()
        for record in records:
            if record["user_id"] == user.user_id:
                wallets = {
                    code: Wallet(code, value["balance"])
                    for code, value in record["wallets"].items()
                }
                return Portfolio(user, wallets)
        raise ValueError("Портфель пользователя не найден")

    def get_rate(self, from_code, to_code):
        """Прочитать курс из последнего сохранённого кэша."""
        get_currency(from_code)
        get_currency(to_code)
        return cached_rate(self.database.read("rates")["pairs"], from_code, to_code)

    def show_portfolio(self, base=None):
        user = self._require_user()
        base = base or self.settings.get("default_base_currency")
        get_currency(base)
        portfolio = self._load_portfolio(self.database.read("portfolios"))
        rows = []
        rates = {}
        for code, wallet in sorted(portfolio.wallets.items()):
            value = 0.0
            if wallet.balance:
                entry = self.get_rate(code, base)
                value = validate_number(wallet.balance * entry["rate"], "value", True)
                rates[code + "_" + base] = entry
            rows.append({"code": code, "balance": wallet.balance, "value": value})
        return {
            "username": user.username,
            "base": base,
            "rows": rows,
            "total": portfolio.get_total_value(base, rates),
        }

    def _trade(self, currency_code, amount, selling):
        self._require_user()
        get_currency(currency_code)
        amount = validate_number(amount)
        records = self.database.read("portfolios")
        portfolio = self._load_portfolio(records)
        wallet = (
            portfolio.get_wallet(currency_code)
            if selling
            else portfolio.add_currency(currency_code)
        )
        before = wallet.balance
        if selling:
            wallet.withdraw(amount)
        else:
            wallet.deposit(amount)
        entry = self.get_rate(currency_code, "USD")
        estimate = validate_number(amount * entry["rate"], "estimate")
        for index, record in enumerate(records):
            if record["user_id"] == portfolio.user.user_id:
                records[index] = portfolio.to_dict()
                break
        self.database.write("portfolios", records)
        return {
            "currency_code": currency_code,
            "amount": amount,
            "before": before,
            "after": wallet.balance,
            "rate": entry["rate"],
            "base": "USD",
            "estimate": estimate,
        }

    @log_action("BUY")
    def buy(self, currency_code, amount):
        """Пополнить виртуальный кошелёк выбранной валюты."""
        return self._trade(currency_code, amount, False)

    @log_action("SELL")
    def sell(self, currency_code, amount):
        """Продать валюту в пределах остатка кошелька."""
        return self._trade(currency_code, amount, True)

    def update_rates(self, source=None):
        return update_rates(source)

    def show_rates(self, currency=None, top=None, base="USD"):
        get_currency(base)
        if currency:
            get_currency(currency)
        if top is not None and (type(top) is not int or top <= 0):
            raise ValueError("--top должен быть положительным целым числом")
        snapshot = self.database.read("rates")
        if not snapshot["pairs"]:
            raise ValueError("Локальный кеш курсов пуст. Выполните update-rates")
        rows = []
        for code in sorted({pair.split("_")[0] for pair in snapshot["pairs"]}):
            if currency and code != currency:
                continue
            if top is not None and not isinstance(CURRENCIES.get(code), CryptoCurrency):
                continue
            entry = cached_rate(snapshot["pairs"], code, base)
            rows.append(
                {
                    "code": code,
                    **entry,
                    "stale": not is_fresh(
                        entry["updated_at"], self.settings.get("rates_ttl_seconds")
                    ),
                }
            )
        if top is not None:
            rows = sorted(rows, key=lambda row: row["rate"], reverse=True)[:top]
        if not rows:
            raise ValueError(f"Курс для '{currency or 'криптовалют'}' не найден в кеше")
        return {"base": base, "last_refresh": snapshot["last_refresh"], "rows": rows}
