from abc import ABC, abstractmethod


class CachePort(ABC):
    @abstractmethod
    def get(self, key: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        raise NotImplementedError
