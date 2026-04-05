"""Shared SSL context builder for Aiven Kafka (used by producer and consumer)."""

import logging
import ssl

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def build_ssl_context() -> ssl.SSLContext | None:
    """Build SSL context from Aiven cert files.

    Returns None if KAFKA_SSL_CAFILE is not configured (dev/non-SSL mode).
    Raises ValueError if only one of certfile/keyfile is provided.
    """
    settings = get_settings()
    if not settings.KAFKA_SSL_CAFILE:
        return None
    ctx = ssl.create_default_context(cafile=settings.KAFKA_SSL_CAFILE)

    has_cert = bool(settings.KAFKA_SSL_CERTFILE)
    has_key = bool(settings.KAFKA_SSL_KEYFILE)
    if has_cert and has_key:
        ctx.load_cert_chain(
            certfile=settings.KAFKA_SSL_CERTFILE,
            keyfile=settings.KAFKA_SSL_KEYFILE,
        )
    elif has_cert != has_key:
        missing = "KAFKA_SSL_KEYFILE" if has_cert else "KAFKA_SSL_CERTFILE"
        raise ValueError(
            f"Incomplete mTLS config: {missing} is missing. "
            "Provide both KAFKA_SSL_CERTFILE and KAFKA_SSL_KEYFILE, or neither."
        )
    return ctx
