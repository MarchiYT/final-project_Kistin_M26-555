import logging

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.core.utils import utc_now, validate_number
from valutatrade_hub.parser_service.api_clients import (
    CoinGeckoClient,
    ExchangeRateApiClient,
)
from valutatrade_hub.parser_service.storage import RatesStorage


class RatesUpdater:
    def __init__(self, clients=None, storage=None):
        self.clients = (
            clients
            if clients is not None
            else [CoinGeckoClient(), ExchangeRateApiClient()]
        )
        self.storage = storage or RatesStorage()

    def run_update(self):
        """Получить курсы выбранных источников и сохранить их."""
        logger = logging.getLogger("valutatrade.parser")
        records = []
        logger.info("Начало обновления")
        try:
            for client in self.clients:
                logger.info("Источник: %s", client.source)
                rates = client.fetch_rates()
                if not rates:
                    raise ApiRequestError(f"{client.source}: пустой ответ")
                timestamp = client.updated_at or utc_now()
                for pair, rate in rates.items():
                    source, target = pair.split("_")
                    records.append(
                        {
                            "id": pair + "_" + timestamp,
                            "from_currency": source,
                            "to_currency": target,
                            "rate": validate_number(rate, "rate"),
                            "timestamp": timestamp,
                            "source": client.source,
                        }
                    )
            if not records:
                raise ApiRequestError("Не выбраны источники курсов")
            refreshed_at = utc_now()
            count = self.storage.save(records, refreshed_at)
        except (ApiRequestError, ValueError, OSError) as error:
            logger.error("Обновление не выполнено: %s", error)
            raise
        logger.info("Сохранено курсов: %s", count)
        return {"count": count, "last_refresh": refreshed_at, "errors": []}


def update_rates(source=None):
    clients = {"coingecko": CoinGeckoClient, "exchangerate": ExchangeRateApiClient}
    if source is not None and source not in clients:
        raise ValueError("Источник: coingecko или exchangerate")
    selected = (
        [clients[source]()] if source else [factory() for factory in clients.values()]
    )
    return RatesUpdater(selected).run_update()
