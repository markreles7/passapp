class AIServiceError(Exception):
    """An error safe to show to the operator without exposing credentials."""


class AIValidationError(AIServiceError):
    pass


def user_message(exc: BaseException) -> str:
    cause = str(exc) if isinstance(exc, AIServiceError) else "Connessione ChatGPT non disponibile."
    return "L'Assistente Operativo non e momentaneamente disponibile.\nI dati di PassApp non sono stati modificati.\n\n" + cause
