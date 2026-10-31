"""Разбор команд и вывод результатов бизнес-операций."""

import argparse
import shlex

from prettytable import PrettyTable

from valutatrade_hub.core.currencies import CURRENCIES
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
)
from valutatrade_hub.core.usecases import TradingService
from valutatrade_hub.logging_config import setup_logging


class CommandParser(argparse.ArgumentParser):
    """Парсер, ошибка которого не завершает основной цикл."""

    def error(self, message):
        """Передать ошибку аргументов обработчику CLI."""
        raise ValueError(f"Ошибка аргументов: {message}")


def build_parser():
    """Описать доступные команды и обязательные аргументы."""
    parser = CommandParser(prog="", add_help=False)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, description in [("register", "Регистрация"), ("login", "Вход")]:
        command = commands.add_parser(name, help=description, add_help=False)
        command.add_argument("--username", required=True)
        command.add_argument("--password", required=True)
    command = commands.add_parser("show-portfolio", help="Портфель", add_help=False)
    command.add_argument("--base", default=None)
    for name in ("buy", "sell"):
        command = commands.add_parser(
            name, help="Покупка" if name == "buy" else "Продажа", add_help=False
        )
        command.add_argument("--currency", required=True)
        command.add_argument("--amount", type=float, required=True)
    command = commands.add_parser(
        "get-rate", help="Курс одной валюты к другой", add_help=False
    )
    command.add_argument("--from", dest="from_code", required=True)
    command.add_argument("--to", dest="to_code", required=True)
    command = commands.add_parser("update-rates", help="Обновить курсы", add_help=False)
    command.add_argument("--source", choices=["coingecko", "exchangerate"])
    command = commands.add_parser(
        "show-rates", help="Список курсов из кэша", add_help=False
    )
    command.add_argument("--currency")
    command.add_argument("--top", type=int)
    command.add_argument("--base", default="USD")
    commands.add_parser("logout", help="Завершить сессию", add_help=False)
    commands.add_parser("exit", help="Выход", add_help=False)
    command = commands.add_parser("help", help="Справка", add_help=False)
    command.add_argument("topic", nargs="?")
    return parser, commands.choices


class CommandInterface:
    """Преобразование команд пользователя в вызовы TradingService."""

    def __init__(self, service=None):
        self.service = service or TradingService()
        self.parser, self.commands = build_parser()

    def execute(self, line):
        """Обработать одну строку; False означает выход."""
        args = self.parser.parse_args(shlex.split(line))
        command = args.command
        if command == "exit":
            return False
        if command == "help":
            self._show_help(args.topic)
        elif command in ("register", "login"):
            result = getattr(self.service, command)(args.username, args.password)
            if command == "register":
                print(
                    f"Пользователь '{result['username']}' зарегистрирован "
                    f"(id={result['user_id']})."
                )
                print("Войдите с помощью login --username ИМЯ --password ПАРОЛЬ")
            else:
                print(f"Вы вошли как '{result['username']}'")
        elif command == "logout":
            self.service.logout()
            print("Вы вышли из учётной записи.")
        elif command == "show-portfolio":
            result = self.service.show_portfolio(args.base)
            self._print_portfolio(result)
        elif command in ("buy", "sell"):
            result = getattr(self.service, command)(args.currency, args.amount)
            self._print_trade(command, result)
        elif command == "get-rate":
            result = self.service.get_rate(args.from_code, args.to_code)
            print(f"Курс {args.from_code}→{args.to_code}: {result['rate']:.8f}")
            print(f"Обновлено: {result['updated_at']}; источник: {result['source']}")
            print(
                f"Обратный курс {args.to_code}→{args.from_code}: "
                f"{1 / result['rate']:.8f}"
            )
        elif command == "update-rates":
            result = self.service.update_rates(args.source)
            print(
                f"Обновлено курсов: {result['count']}. Время: {result['last_refresh']}"
            )
            for error in result["errors"]:
                print(error)
            if result["errors"]:
                print("Обновление завершено с ошибками. Подробности: logs/parser.log")
            else:
                print("Обновление завершено успешно.")
        elif command == "show-rates":
            result = self.service.show_rates(args.currency, args.top, args.base)
            self._print_rates(result)
        return True

    def _show_help(self, topic):
        if topic:
            choices = self.commands
            if topic not in choices:
                raise ValueError(f"Неизвестная команда '{topic}'")
            choices[topic].print_help()
        else:
            self.parser.print_help()
            print("Валюты: " + ", ".join(CURRENCIES))
            print("Пример: buy --currency EUR --amount 100")

    @staticmethod
    def _print_portfolio(result):
        if not result["rows"]:
            print("Портфель пуст. Добавьте валюту командой buy.")
            return
        print(f"Портфель пользователя '{result['username']}' (база: {result['base']}):")
        table = PrettyTable(["Валюта", "Баланс", f"Стоимость в {result['base']}"])
        for row in result["rows"]:
            table.add_row([row["code"], f"{row['balance']:.8f}", f"{row['value']:.2f}"])
        print(table)
        print(f"ИТОГО: {result['total']:.2f} {result['base']}")

    @staticmethod
    def _print_trade(command, result):
        name = "Покупка" if command == "buy" else "Продажа"
        code = result["currency_code"]
        print(f"{name} выполнена: {result['amount']:.8f} {code}")
        print(f"Курс: {result['rate']:.8f} USD/{code}")
        print(f"{code}: было {result['before']:.8f} → стало {result['after']:.8f}")
        label = (
            "Оценочная стоимость покупки" if command == "buy" else "Оценочная выручка"
        )
        print(f"{label}: {result['estimate']:.2f} USD")

    @staticmethod
    def _print_rates(result):
        print(f"Курсы из кэша. Последнее обновление: {result['last_refresh']}")
        table = PrettyTable(["Пара", "Курс", "Обновлено (UTC)", "Состояние"])
        for row in result["rows"]:
            table.add_row(
                [
                    f"{row['code']}_{result['base']}",
                    f"{row['rate']:.8f}",
                    row["updated_at"],
                    "устарел" if row["stale"] else "актуален",
                ]
            )
        print(table)
        if any(row["stale"] for row in result["rows"]):
            print("Есть устаревшие данные. Выполните update-rates.")


def run():
    """Запустить цикл ввода с обработкой ошибок отдельных команд."""
    try:
        setup_logging()
        interface = CommandInterface()
    except (OSError, ValueError) as error:
        print(f"Не удалось запустить приложение: {error}")
        return
    print("ValutaTrade Hub. Введите help для справки, exit для выхода.")
    while True:
        try:
            line = input("> ").strip()
            if line and not interface.execute(line):
                break
        except (EOFError, KeyboardInterrupt):
            print("\nДо свидания!")
            break
        except CurrencyNotFoundError as error:
            print(error)
            print(
                "Поддерживаются: " + ", ".join(CURRENCIES) + ". Справка: help get-rate"
            )
        except InsufficientFundsError as error:
            print(error)
        except ApiRequestError as error:
            print(error)
            print("Проверьте сеть и повторите update-rates позже.")
        except (ValueError, TypeError, KeyError, OSError) as error:
            print(f"Ошибка: {error}")
