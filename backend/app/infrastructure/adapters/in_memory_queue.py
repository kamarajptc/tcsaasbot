from typing import Any

from app.infrastructure.ports.queue import QueuePort


class InMemoryQueue(QueuePort):
    def __init__(self):
        self.messages: list[dict[str, Any]] = []

    def enqueue(self, topic: str, payload: dict[str, Any]) -> None:
        self.messages.append({"topic": topic, "payload": payload})
