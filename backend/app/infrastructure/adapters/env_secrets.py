import os

from app.infrastructure.ports.secrets import SecretsPort


class EnvSecrets(SecretsPort):
    def get_secret(self, name: str, default: str = "") -> str:
        return os.getenv(name, default)
