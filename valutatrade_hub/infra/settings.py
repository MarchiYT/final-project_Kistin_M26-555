"""Единые настройки приложения."""

import os
import tomllib
from pathlib import Path

DEFAULTS = {
    "data_dir": "data",
    "logs_dir": "logs",
    "rates_ttl_seconds": 300,
    "default_base_currency": "USD",
    "log_level": "INFO",
    "log_format": "%(asctime)s %(levelname)s %(message)s",
}


class SettingsLoader:
    """Один набор настроек на процесс, создаваемый через __new__."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.reload()
        return cls._instance

    def reload(self):
        """Прочитать настройки из pyproject.toml и окружения."""
        values = DEFAULTS.copy()
        path = Path.cwd() / "pyproject.toml"
        if path.is_file():
            with path.open("rb") as file:
                values.update(tomllib.load(file).get("tool", {}).get("valutatrade", {}))
        for key in DEFAULTS:
            raw = os.getenv("VALUTATRADE_" + key.upper())
            if raw is not None:
                values[key] = int(raw) if type(DEFAULTS[key]) is int else raw
        for key in ("rates_ttl_seconds",):
            if type(values[key]) is not int or values[key] <= 0:
                raise ValueError(
                    f"Настройка {key} должна быть положительным целым числом"
                )
        self._values = values

    def get(self, key, default=None):
        """Получить настройку или указанное значение по умолчанию."""
        return self._values.get(key, default)

    def data_path(self, name):
        """Составить путь к одному JSON-файлу данных."""
        return Path(self.get("data_dir")) / (name + ".json")
