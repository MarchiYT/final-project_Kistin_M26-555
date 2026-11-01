import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests

from valutatrade_hub.cli.interface import CommandInterface
from valutatrade_hub.core.exceptions import ApiRequestError, InsufficientFundsError
from valutatrade_hub.core.models import User, Wallet
from valutatrade_hub.core.usecases import TradingService
from valutatrade_hub.core.utils import utc_now
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.api_clients import (
    CoinGeckoClient,
    ExchangeRateApiClient,
)
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.storage import RatesStorage
from valutatrade_hub.parser_service.updater import RatesUpdater


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.environment = patch.dict(
            os.environ,
            {
                "VALUTATRADE_DATA_DIR": str(self.directory),
            },
        )
        self.environment.start()
        SettingsLoader._instance = None
        self.database = DatabaseManager()
        self.service = TradingService(self.database)
        self.seed_rates()

    def tearDown(self):
        self.environment.stop()
        SettingsLoader._instance = None
        self.temporary.cleanup()

    def seed_rates(self, timestamp=None):
        timestamp = timestamp or utc_now()
        self.database.write(
            "rates",
            {
                "pairs": {
                    code + "_USD": {
                        "rate": rate,
                        "updated_at": timestamp,
                        "source": "test",
                    }
                    for code, rate in {"EUR": 1.1, "GBP": 1.25, "BTC": 60000}.items()
                },
                "last_refresh": timestamp,
            },
        )

    def login(self):
        self.service.register("alice", "1234")
        self.service.login("alice", "1234")

    def response(self, data, status=200):
        response = Mock(status_code=status)
        response.json.return_value = data
        return response

    def test_password_hash_and_salt(self):
        first = User.create(1, "alice", "1234")
        second = User.create(2, "bob", "1234")
        self.assertNotEqual(first.salt, second.salt)
        self.assertNotEqual(first.hashed_password, second.hashed_password)
        self.assertTrue(first.verify_password("1234"))
        first.change_password("5678")
        self.assertFalse(first.verify_password("1234"))
        self.assertTrue(first.verify_password("5678"))
        self.assertNotIn("hashed_password", first.get_user_info())

    def test_invalid_user(self):
        for username, password in [("", "1234"), ("alice", "123"), ("   ", "1234")]:
            with self.assertRaises(ValueError):
                User.create(1, username, password)

    def test_wallet_validation_and_balance(self):
        wallet = Wallet("EUR", 10)
        wallet.deposit(2)
        wallet.withdraw(3)
        self.assertEqual(wallet.balance, 9)
        with self.assertRaises(InsufficientFundsError):
            wallet.withdraw(10)
        for amount in [-1, 0, True, float("nan"), float("inf")]:
            with self.assertRaises(ValueError):
                wallet.deposit(amount)
        self.assertEqual(wallet.balance, 9)

    def test_register_and_login(self):
        with self.assertRaises(ValueError):
            self.service.show_portfolio()
        self.login()
        with self.assertRaises(ValueError):
            self.service.register("alice", "1234")
        with self.assertRaises(ValueError):
            self.service.login("alice", "wrong")
        self.assertEqual(self.service.current_user.username, "alice")
        self.assertEqual(self.service.show_portfolio()["rows"], [])

    def test_buy_sell_and_portfolio(self):
        self.login()
        self.service.buy("EUR", 100)
        self.service.buy("BTC", 0.01)
        self.service.sell("EUR", 25)
        self.assertAlmostEqual(self.service.show_portfolio()["total"], 682.5)
        self.assertAlmostEqual(self.service.show_portfolio("EUR")["total"], 682.5 / 1.1)

    def test_failed_trade_does_not_save(self):
        self.login()
        self.service.buy("EUR", 10)
        before = self.database.read("portfolios")
        with self.assertRaises(InsufficientFundsError):
            self.service.sell("EUR", 11)
        with self.assertRaises(ValueError):
            self.service.buy("EUR", -1)
        with self.assertRaises(ApiRequestError):
            self.service.buy("SOL", 1)
        self.assertEqual(self.database.read("portfolios"), before)

    def test_direct_inverse_and_cross_rates(self):
        self.assertEqual(self.service.get_rate("BTC", "USD")["rate"], 60000)
        self.assertAlmostEqual(self.service.get_rate("USD", "EUR")["rate"], 1 / 1.1)
        self.assertAlmostEqual(self.service.get_rate("EUR", "GBP")["rate"], 1.1 / 1.25)

    def test_old_rates_are_marked_and_not_updated_automatically(self):
        self.seed_rates("2000-01-01T00:00:00Z")
        with patch("valutatrade_hub.core.usecases.update_rates") as update:
            self.assertEqual(self.service.get_rate("EUR", "USD")["rate"], 1.1)
            update.assert_not_called()
        self.assertTrue(all(row["stale"] for row in self.service.show_rates()["rows"]))

    def test_users_have_separate_wallets(self):
        self.login()
        self.service.buy("EUR", 20)
        self.service.register("bob", "1234")
        self.service.login("bob", "1234")
        self.assertEqual(self.service.show_portfolio()["rows"], [])
        self.service.login("alice", "1234")
        self.assertEqual(self.service.show_portfolio()["rows"][0]["balance"], 20)

    def test_coingecko_client(self):
        response = self.response(
            {
                "bitcoin": {"usd": 60000},
                "ethereum": {"usd": 3000},
                "solana": {"usd": 150},
            }
        )
        with patch(
            "valutatrade_hub.parser_service.api_clients.requests.get",
            return_value=response,
        ) as request:
            self.assertEqual(CoinGeckoClient().fetch_rates()["BTC_USD"], 60000)
        self.assertEqual(request.call_args.kwargs["timeout"], 10)
        response.close.assert_called_once()

    def test_exchange_api_inverts_rates(self):
        config = ParserConfig()
        config.EXCHANGERATE_API_KEY = ""
        response = self.response(
            {
                "result": "success",
                "base_code": "USD",
                "rates": {"EUR": 0.8, "GBP": 0.5, "RUB": 100},
            }
        )
        with patch(
            "valutatrade_hub.parser_service.api_clients.requests.get",
            return_value=response,
        ):
            rates = ExchangeRateApiClient(config).fetch_rates()
        self.assertEqual(rates["EUR_USD"], 1.25)
        self.assertEqual(rates["RUB_USD"], 0.01)

    def test_api_errors(self):
        with patch(
            "valutatrade_hub.parser_service.api_clients.requests.get",
            side_effect=requests.Timeout(),
        ):
            with self.assertRaises(ApiRequestError):
                CoinGeckoClient().fetch_rates()
        with patch(
            "valutatrade_hub.parser_service.api_clients.requests.get",
            return_value=self.response({}, 429),
        ):
            with self.assertRaises(ApiRequestError):
                CoinGeckoClient().fetch_rates()

    def test_update_combines_sources(self):
        clients = [
            SimpleNamespace(
                source="first",
                updated_at=utc_now(),
                fetch_rates=lambda: {"EUR_USD": 1.2},
            ),
            SimpleNamespace(
                source="second",
                updated_at=utc_now(),
                fetch_rates=lambda: {"BTC_USD": 60000},
            ),
        ]
        result = RatesUpdater(clients, RatesStorage(self.database)).run_update()
        self.assertEqual(result["count"], 2)
        self.assertEqual(len(self.database.read("exchange_rates")), 2)

    def test_failed_update_keeps_previous_cache(self):
        before = self.database.read("rates")
        client = SimpleNamespace(
            source="test", fetch_rates=Mock(side_effect=ApiRequestError("offline"))
        )
        with self.assertRaises(ApiRequestError):
            RatesUpdater([client], RatesStorage(self.database)).run_update()
        self.assertEqual(before, self.database.read("rates"))

    def test_last_measurements_replace_previous_batch(self):
        storage = RatesStorage(self.database)

        def record(code):
            return {
                "from_currency": code,
                "to_currency": "USD",
                "rate": 1.2,
                "timestamp": utc_now(),
                "source": "test",
            }

        storage.save([record("EUR")], utc_now())
        storage.save([record("GBP")], utc_now())
        self.assertEqual(len(self.database.read("exchange_rates")), 1)
        self.assertEqual(
            self.database.read("exchange_rates")[0]["from_currency"], "GBP"
        )

    def test_invalid_json_is_not_overwritten(self):
        path = self.directory / "users.json"
        path.write_text("broken", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.service.register("alice", "1234")
        self.assertEqual(path.read_text(), "broken")

    def test_cli_handles_arguments(self):
        interface = CommandInterface(self.service)
        with contextlib.redirect_stdout(io.StringIO()):
            interface.execute("register --username alice --password 1234")
            interface.execute("login --username alice --password 1234")
            interface.execute("buy --currency EUR --amount 10")
            interface.execute("show-portfolio")
            interface.execute("help buy")
        with self.assertRaises(ValueError):
            interface.execute("buy --currency EUR")
        self.assertFalse(interface.execute("exit"))

    def test_trade_logging(self):
        self.login()
        with self.assertLogs("valutatrade.actions", level="INFO") as logs:
            self.service.buy("EUR", 2)
            with self.assertRaises(InsufficientFundsError):
                self.service.sell("EUR", 3)
        self.assertIn("result=OK", logs.output[0])
        self.assertIn("result=ERROR", logs.output[1])
        self.assertNotIn("1234", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()
