import unittest
from unittest.mock import MagicMock
from tenacity import RetryError
from google.api_core import exceptions
import sys
import os

# Adjust path to import modules from parent directory
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from ocr_utils import retry_gemini_call

class TestOCRRetryLogic(unittest.TestCase):

    def test_retry_success(self):
        """Test that retry eventually succeeds after failures"""
        mock = MagicMock()
        # Fail twice with ResourceExhausted, then succeed
        mock.side_effect = [
            exceptions.ResourceExhausted("429 error"),
            exceptions.ResourceExhausted("429 error again"),
            "Success"
        ]

        @retry_gemini_call(max_attempts=5, min_wait=0, max_wait=0)
        def _test_func():
            return mock()

        result = _test_func()
        self.assertEqual(result, "Success")
        self.assertEqual(mock.call_count, 3)

    def test_retry_failure(self):
        """Test that retry gives up after max attempts and reraises the last exception"""
        mock = MagicMock()
        mock.side_effect = exceptions.InternalServerError("500 error")

        @retry_gemini_call(max_attempts=3, min_wait=0, max_wait=0)
        def _test_func_fail():
            return mock()

        # tenacity with reraise=True raises the original exception
        with self.assertRaises(exceptions.InternalServerError):
            _test_func_fail()
        
        self.assertEqual(mock.call_count, 3)

    def test_no_retry_on_fatal(self):
        """Test that non-retryable exceptions pass through immediately"""
        mock = MagicMock()
        mock.side_effect = exceptions.InvalidArgument("400 error")

        @retry_gemini_call(max_attempts=3)
        def _test_func_fatal():
            return mock()

        try:
            _test_func_fatal()
            self.fail("InvalidArgument not raised")
        except exceptions.InvalidArgument:
            pass
        
        self.assertEqual(mock.call_count, 1)

if __name__ == '__main__':
    unittest.main()
