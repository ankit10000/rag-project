"""Experimental WP7 preparation; frozen evaluation entry points stay unchanged.

Importing this namespace does not select a scorer, read inputs, run providers,
or adopt any pending scoring or acceptance policy.
"""

from .selection import select_scorer

__all__ = ['select_scorer']
