from abc import ABC, abstractmethod
from typing import Any


class QueuePort(ABC):
    @abstractmethod
    def enqueue(self, topic: str, payload: dict[str, Any]) -> None:
        raise NotImplementedError
