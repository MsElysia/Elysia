"""Minimal openai stub for construct/activate tests (no live providers)."""


class OpenAIError(Exception):
    pass


class APIError(OpenAIError):
    pass


class RateLimitError(OpenAIError):
    pass


class AuthenticationError(OpenAIError):
    pass


class ChatCompletion:
    @staticmethod
    def create(*args, **kwargs):
        raise OpenAIError("stub openai: no live providers")


class Chat:
    completions = ChatCompletion


class Completions:
    @staticmethod
    def create(*args, **kwargs):
        raise OpenAIError("stub openai: no live providers")


class OpenAI:
    def __init__(self, *args, **kwargs):
        self.chat = Chat()
        self.completions = Completions()


api_key = None
__version__ = "0.0.0-stub"
