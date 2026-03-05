from abc import ABC, abstractmethod


class SecretsPort(ABC):
    @abstractmethod
    def get_secret(self, name: str, default: str = "") -> str:
        raise NotImplementedError
