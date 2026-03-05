from pathlib import Path

from app.infrastructure.ports.storage import ObjectStorage


class LocalObjectStorage(ObjectStorage):
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def put_text(self, key: str, content: str) -> str:
        target = self.base_dir / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return str(target)

    def get_text(self, key: str) -> str:
        return (self.base_dir / key).read_text(encoding="utf-8")
