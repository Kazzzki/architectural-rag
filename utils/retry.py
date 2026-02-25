import asyncio
import functools
import logging
import time

logger = logging.getLogger(__name__)

def async_retry(max_retries: int = 3, base_wait: float = 2.0, exceptions: tuple = (Exception,)):
    """非同期関数用 指数バックオフリトライデコレータ"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_error = e
                    wait = base_wait ** attempt
                    logger.warning(f"[{func.__name__}] 試行{attempt+1}/{max_retries}: {type(e).__name__}: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(wait)
            raise RuntimeError(f"[{func.__name__}] {max_retries}回失敗: {last_error}")
        return wrapper
    return decorator

def sync_retry(max_retries: int = 3, base_wait: float = 2.0, exceptions: tuple = (Exception,)):
    """同期関数（バックグラウンドパイプライン）用指数バックオフリトライデコレータ"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_error = e
                    wait = base_wait ** attempt
                    logger.warning(f"[{func.__name__}] 試行{attempt+1}/{max_retries}: {type(e).__name__}: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(wait)
            raise RuntimeError(f"[{func.__name__}] {max_retries}回失敗: {last_error}")
        return wrapper
    return decorator
