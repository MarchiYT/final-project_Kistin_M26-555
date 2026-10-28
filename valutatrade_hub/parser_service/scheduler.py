import argparse

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.logging_config import setup_logging
from valutatrade_hub.parser_service.updater import update_rates


def main():
    parser = argparse.ArgumentParser(description="Однократное обновление курсов")
    parser.add_argument("--source", choices=["coingecko", "exchangerate"])
    args = parser.parse_args()
    setup_logging()
    try:
        result = update_rates(args.source)
        print(f"Обновлено курсов: {result['count']}")
        return 0
    except (ApiRequestError, OSError, ValueError) as error:
        print(error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
