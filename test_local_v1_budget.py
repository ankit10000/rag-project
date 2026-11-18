"""Budget propagation and bounded waits without provider calls or a database."""
import testsafe
testsafe.require_scratch_db()
import contextvars
import threading
import unittest
from unittest.mock import patch
from services import request_budget as B


class BudgetTests(unittest.TestCase):
    def test_no_budget_keeps_existing_timeout(self):
        self.assertIsNone(B.remaining_seconds())
        self.assertEqual(B.http_timeout_ms(120000),120000)

    def test_absolute_budget_covers_sequential_calls(self):
        now=[10.0]
        with patch.object(B.time,'monotonic',side_effect=lambda:now[0]):
            with self.assertRaises(B.RequestDeadlineExceeded),B.request_budget(2):
                self.assertEqual(B.http_timeout_ms(120000),2000)
                now[0]+=1.5
                self.assertEqual(B.http_timeout_ms(120000),500)
                now[0]+=0.6
                B.check_deadline()
        self.assertIsNone(B.remaining_seconds())

    def test_retry_wait_cannot_consume_or_extend_deadline(self):
        with B.request_budget(1):
            with self.assertRaises(B.RequestDeadlineExceeded):B.pause(10,lambda _:self.fail('must not sleep'))

    def test_nested_budget_and_output_scope_reset(self):
        with B.request_budget(2,suppress_output=True):
            prior=B.remaining_seconds()
            with B.request_budget(50):
                self.assertLessEqual(B.remaining_seconds(),prior)
                self.assertTrue(B.output_suppressed())
        self.assertFalse(B.output_suppressed())

    def test_lock_wait_times_out_without_stealing_lock(self):
        lock=threading.Lock();lock.acquire()
        try:
            with self.assertRaises(B.RequestDeadlineExceeded),B.request_budget(0.01):
                with B.budgeted_lock(lock):self.fail('unavailable lock acquired')
            self.assertTrue(lock.locked())
        finally:lock.release()

    def test_context_copy_for_worker_preserves_absolute_deadline(self):
        with B.request_budget(2,suppress_output=True):
            copied=contextvars.copy_context()
            self.assertTrue(copied.run(B.output_suppressed))
            self.assertLessEqual(copied.run(B.remaining_seconds),2)

    def test_invalid_configuration_and_exception_reset(self):
        for value in ['nan','inf','0','-1','301','invalid']:
            with self.subTest(value=value),patch.dict('os.environ',LOCAL_V1_REQUEST_TIMEOUT_SECONDS=value):
                with self.assertRaises(ValueError):B.configured_timeout()
        with self.assertRaises(RuntimeError),B.request_budget(1):raise RuntimeError('fixture')
        self.assertIsNone(B.remaining_seconds())


if __name__=='__main__':unittest.main()
