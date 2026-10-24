import logging
from functools import wraps


def log_action(action):
    """Записать результат покупки или продажи."""

    def decorate(function):
        @wraps(function)
        def wrapped(self, currency_code, amount):
            user = self.current_user.username if self.current_user else "-"
            logger = logging.getLogger("valutatrade.actions")
            try:
                result = function(self, currency_code, amount)
            except Exception as error:
                logger.info(
                    "%s user=%r currency=%s amount=%s result=ERROR %s: %s",
                    action,
                    user,
                    currency_code,
                    amount,
                    type(error).__name__,
                    error,
                )
                raise
            logger.info(
                "%s user=%r currency=%s amount=%s rate=%s base=USD result=OK",
                action,
                user,
                currency_code,
                amount,
                result["rate"],
            )
            return result

        return wrapped

    return decorate
