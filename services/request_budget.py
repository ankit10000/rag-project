"""Cooperative local request budget; never abandons a still-writing worker."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import math
import os
import time

_current = ContextVar('local_request_budget', default=None)


class RequestDeadlineExceeded(TimeoutError):
    def __init__(self):
        super().__init__('local request deadline exceeded')


def configured_timeout():
    value = float(os.getenv('LOCAL_V1_REQUEST_TIMEOUT_SECONDS', '60'))
    if not math.isfinite(value) or not 0 < value <= 300:
        raise ValueError('LOCAL_V1_REQUEST_TIMEOUT_SECONDS must be in (0, 300]')
    return value


def remaining_seconds():
    state = _current.get()
    if state is None:
        return None
    remaining = state[0] - time.monotonic()
    if remaining <= 0:
        raise RequestDeadlineExceeded()
    return remaining


def check_deadline():
    remaining_seconds()


def output_suppressed():
    state = _current.get()
    return bool(state and state[1])


def timeout_seconds(maximum):
    remaining = remaining_seconds()
    return maximum if remaining is None else min(maximum, remaining)


def http_timeout_ms(maximum):
    return max(1, int(timeout_seconds(maximum / 1000) * 1000))


def pause(seconds, sleep_fn=None):
    remaining = remaining_seconds()
    if remaining is not None and seconds >= remaining:
        raise RequestDeadlineExceeded()
    (sleep_fn or time.sleep)(seconds)
    check_deadline()


@contextmanager
def request_budget(seconds=None, *, suppress_output=False):
    seconds = configured_timeout() if seconds is None else seconds
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds <= 0:
        raise ValueError('positive finite request budget required')
    prior = _current.get()
    deadline = time.monotonic() + seconds
    if prior:
        deadline = min(deadline, prior[0])
        suppress_output = suppress_output or prior[1]
    token = _current.set((deadline, bool(suppress_output)))
    try:
        check_deadline()
        yield
        check_deadline()
    finally:
        _current.reset(token)


@contextmanager
def budgeted_lock(lock):
    remaining = remaining_seconds()
    acquired = lock.acquire() if remaining is None else lock.acquire(timeout=remaining)
    if not acquired:
        raise RequestDeadlineExceeded()
    try:
        check_deadline()
        yield
    finally:
        lock.release()


def within_turn_budget(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        # Existing CLI/test behavior is retained outside the explicit release profile.
        if _current.get() is None and os.getenv('LOCAL_V1_PROFILE') == '1':
            with request_budget():
                return function(*args, **kwargs)
        check_deadline()
        result = function(*args, **kwargs)
        check_deadline()
        return result
    return wrapped
