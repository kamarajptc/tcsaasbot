# Modular Monolith Shell

This package defines the target module boundaries for the backend.

Rules:
- Existing FastAPI routers remain stable during the refactor.
- New code should be added through module APIs rather than directly under `app/api` or `app/services`.
- Cross-module access must happen through public interfaces only.
