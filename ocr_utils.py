import time
import logging
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)
from google.api_core import exceptions

# ロガーの設定
logger = logging.getLogger(__name__)

# リトライすべき例外の定義
# ResourceExhausted (429), InternalServerError (500), ServiceUnavailable (503), GatewayTimeout (504)
RETRYABLE_EXCEPTIONS = (
    exceptions.ResourceExhausted,
    exceptions.InternalServerError,
    exceptions.ServiceUnavailable,
    exceptions.GatewayTimeout,
    exceptions.Aborted,
    exceptions.DeadlineExceeded,
)

def retry_gemini_call(max_attempts: int = 5, min_wait: int = 1, max_wait: int = 16):
    """
    Gemini API呼び出し用のリトライデコレータ
    - 指数バックオフ (1s, 2s, 4s, 8s, 16s...)
    - 最大5回リトライ
    - 特定のエラーコードのみリトライ
    """
    return retry(
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )
