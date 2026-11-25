"""Read an explicitly linked, authoritative amendment to a named amount."""
import re


_REQUEST = re.compile(r"what is (?:the )?current (?P<field>[\w -]{3,70})\s*\?", re.I)
_AMOUNT = r"\d{1,9}(?:\.\d{1,2})?"
_UNIT = r"credits?|dollars?|euros?|rupees?"


def current_amount_answer(question, sources):
    """The old and new values, unit, named subject and supersession must agree.

    Ordinary chronology, retrieval order and words like 'updated' are
    insufficient. Conflicting amendments or assignments defer to normal
    conflict handling.
    """
    request = _REQUEST.fullmatch(question.strip())
    if not request:
        return None
    field = request['field'].strip()
    terms = field.split()
    if not 2 <= len(terms) <= 7:
        return None
    name = re.escape(field)
    noun = re.escape(terms[-1])
    original = re.compile(rf'original {name}\s*:\s*(?P<value>{_AMOUNT})\s+(?P<unit>{_UNIT})[.!]?', re.I)
    update = re.compile(
        rf'official (?:erratum|correction|amendment) to (?:the )?{name}:\s*'
        rf'(?:the )?(?P<new>{_AMOUNT})-(?P<unit>{_UNIT}) {noun} supersedes '
        rf'the original (?P<old>{_AMOUNT})-(?P<old_unit>{_UNIT}) {noun}[.!]?', re.I)
    originals, revisions = set(), {}
    for source in sources:
        ref = source.get('ref')
        if not ref:
            continue
        for line in re.split(r'(?<=[.!?])\s+|[\n;]+', source.get('content', '')):
            if not re.search(rf'\b{name}\b', line, re.I):
                continue
            old = original.fullmatch(line.strip())
            change = update.fullmatch(line.strip())
            if old:
                originals.add((old['value'], old['unit'].lower().rstrip('s')))
            elif change and change['unit'].lower().rstrip('s') == change['old_unit'].lower().rstrip('s'):
                key = (change['old'], change['new'], change['unit'].lower().rstrip('s'))
                revisions.setdefault(key, ref)
            else:
                # Another substantive assertion about the same named field
                # may describe a competing update or a conditional exception.
                return None
    if len(revisions) != 1 or len(originals) != 1:
        return None
    (old, new, unit), ref = next(iter(revisions.items()))
    if originals != {(old, unit)} or old == new:
        return None
    units = unit if new == '1' else unit + 's'
    return f'The current {field} is {new} {units}, according to the official correction [{ref}].'
