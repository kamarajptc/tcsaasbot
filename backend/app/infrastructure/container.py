from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.infrastructure.adapters.env_secrets import EnvSecrets
from app.infrastructure.adapters.in_memory_queue import InMemoryQueue
from app.infrastructure.adapters.local_storage import LocalObjectStorage
from app.infrastructure.adapters.redis_cache import RedisCache


class InfrastructureContainer:
    def __init__(self):
        settings = get_settings()
        artifact_dir = Path(settings.ARTIFACTS_DIR)
        self.object_storage = LocalObjectStorage(str(artifact_dir))
        self.queue = InMemoryQueue()
        self.cache = RedisCache(settings.REDIS_URL)
        self.secrets = EnvSecrets()


@lru_cache
def get_container() -> InfrastructureContainer:
    return InfrastructureContainer()
