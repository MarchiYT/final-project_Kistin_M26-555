"""Чтение и сохранение файлов базы."""

import json
import os

from valutatrade_hub.infra.settings import SettingsLoader


class DatabaseManager:
    def __init__(self):
        self.settings = SettingsLoader()

    def read(self, name):
        path = self.settings.data_path(name)
        if not path.exists():
            return {"pairs": {}, "last_refresh": None} if name == "rates" else []
        try:
            with path.open(encoding="utf-8") as file:
                result = json.load(file)
        except (ValueError, UnicodeError) as error:
            raise ValueError(f"Не удалось прочитать {path.name}") from error
        expected = dict if name == "rates" else list
        if not isinstance(result, expected):
            raise ValueError(f"Неверный формат файла {path.name}")
        if name == "rates" and not isinstance(result.get("pairs"), dict):
            raise ValueError("В rates.json отсутствует словарь pairs")
        return result

    def write(self, name, data):
        """Заменить один JSON-файл через временный файл."""
        path = self.settings.data_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2, allow_nan=False)
                file.write("\n")
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()
