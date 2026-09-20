import ssl
from functools import lru_cache
from typing import Optional


@lru_cache(maxsize=1)
def default_ssl_context() -> Optional[ssl.SSLContext]:
    context = ssl.create_default_context()
    if context.cert_store_stats().get("x509_ca"):
        return context
    try:
        import certifi
    except ImportError:
        return context
    return ssl.create_default_context(cafile=certifi.where())
