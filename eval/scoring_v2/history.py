"""Explicit user grounding and assistant echo separation (§8)."""
from .numbers import G, grounded


def split_history(history):
    if not isinstance(history,list): raise ValueError('history must be a list')
    user,assistant = [],[]
    for turn in history:
        if not isinstance(turn,dict) or turn.get('role') not in ('user','assistant') or not isinstance(turn.get('content'),str):
            raise ValueError('history turns require user/assistant role and string content')
        (user if turn['role']=='user' else assistant).extend(G(turn['content']))
    return user,assistant


def history_echo(tokens, allowed, assistant, corrected=()):
    corrected = set(corrected)
    return sorted({t.display for t in tokens if t not in corrected and t.kind not in ('ref','code') and not grounded(t,allowed) and grounded(t,assistant)})
