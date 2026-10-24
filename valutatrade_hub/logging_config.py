import logging
import time
from pathlib import Path

from valutatrade_hub.infra.settings import SettingsLoader


def setup_logging():
    settings = SettingsLoader()
    directory = Path(settings.get("logs_dir"))
    directory.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        settings.get("log_format"), datefmt="%Y-%m-%dT%H:%M:%SZ"
    )
    formatter.converter = time.gmtime
    for name in ("actions", "parser"):
        logger = logging.getLogger("valutatrade." + name)
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)
        handler = logging.FileHandler(directory / (name + ".log"), encoding="utf-8")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(settings.get("log_level"))
        logger.propagate = False
