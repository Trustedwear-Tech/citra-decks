# citra-cache

Shared Redis cache manager. Replaces what used to be
`Citra-Service/cache_manager.py` imported across services via PYTHONPATH.

## Usage

```python
from citra_cache import get_cache_manager

cache = get_cache_manager()
cache.set("k", "v", ttl=60)
val = cache.get("k")
```

## Env vars

Same Redis env vars as `citra-queue` — shares the same cluster:

| Var | Default |
|---|---|
| `REDIS_HOST` | `localhost` |
| `REDIS_PORT` | `6379` |
| `REDIS_DB` | `0` |
| `REDIS_PASSWORD` | (none) |
| `REDIS_KEY_PREFIX` | `""` |
