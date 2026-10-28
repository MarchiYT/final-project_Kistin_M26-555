from valutatrade_hub.infra.database import DatabaseManager


class RatesStorage:
    def __init__(self, database=None):
        self.database = database or DatabaseManager()

    def save(self, records, refreshed_at):
        """Сохранить последний набор измерений и обновить кэш."""
        snapshot = self.database.read("rates")
        for record in records:
            key = record["from_currency"] + "_" + record["to_currency"]
            snapshot["pairs"][key] = {
                "rate": record["rate"],
                "updated_at": record["timestamp"],
                "source": record["source"],
            }
        snapshot["last_refresh"] = refreshed_at
        self.database.write("exchange_rates", records)
        self.database.write("rates", snapshot)
        return len(records)
