"""Narrow reporting heuristics for missing evidence versus negative facts.

These rules do not establish semantic entailment. In particular, a statement
that a document omits an attribute does not establish that a service does not
exist. Source alignment is limited to the same object in actually cited text.
"""
import re

_MARKER = re.compile(r"\[\s*[Ss]\d+(?:\s*[,;]\s*[Ss]\d+)*\s*\]")
_CLAUSE = re.compile(
    r"\s*;\s*|\s*,?\s+\b(?:but|however|whereas|although|yet|therefore|so)\b\s+"
    r"|\s+and\s+(?=[A-Za-z][\w'-]*(?:\s+[A-Za-z][\w'-]*){0,4}\s+"
    r"(?:is|are|was|were|has|have|costs?|provides?|does|do)\b)", re.I)
_DOC_SUBJECT = re.compile(
    r"^(?:(?:the|these|this|provided|retrieved|available)\s+)*"
    r"(?:documents?|polic(?:y|ies)|passages?|sources?|reports?|text|material|extracts?)$", re.I)
_NEGATED_VERB = re.compile(
    r"^(?P<subject>.+?)\s+(?:does\s+not|doesn't|do\s+not|don't)\s+"
    r"(?P<verb>provide|specify|state|list|mention|give|contain|include|say)\s+"
    r"(?P<object>.+)$", re.I)
_INFORMATION = re.compile(
    r"\b(?:information|details?|answers?|numbers?|addresses?|dates?|times?|"
    r"prices?|fees?|costs?|rates?|amounts?|duration|deadlines?|windows?|notice period)\b", re.I)
_FIRST_PERSON = re.compile(
    r"^(?:i|we)\s+(?:could(?:n't|\s+not)|can(?:not|'t)|am\s+unable\s+to|are\s+unable\s+to)\s+find\b", re.I)
_FRAGMENT = re.compile(
    r"^(?:not (?:available|provided|stated|mentioned|specified)|"
    r"(?:not enough|insufficient|no) information)(?:[.!?]|$)", re.I)
_PASSIVE_GAP = re.compile(r"\b(?:is|are|was|were)\s+not\s+(?:available|provided|stated|mentioned|specified)\b", re.I)
_PASSIVE_REPORT = re.compile(r"\b(?:is|are|was|were)\s+not\s+(?:stated|mentioned|specified)\b", re.I)
_DOC_LOCATION = re.compile(r"\b(?:in|from|by)\s+(?:(?:the|these|this|provided|retrieved|available)\s+)*"
                           r"(?:documents?|polic(?:y|ies)|passages?|sources?|reports?|text|material)\b", re.I)


def _clean(text):
    if not isinstance(text, str):
        return ""
    return " ".join(_MARKER.sub("", text).replace("’", "'").strip(" \t-*•").split()).rstrip(".!?")


def _core(text):
    # Attribution is not the grammatical subject of the negative statement.
    text = re.sub(r"^(?:(?:i(?:'m| am)\s+)?sorry|unfortunately)(?:[, :]+(?:but\s+)?|$)",
                  "", _clean(text), flags=re.I)
    return re.sub(r"^according to [^,]+,\s*", "", text, flags=re.I)


def is_discourse_clause(text):
    return not _core(text)


def _information_object(text):
    # Check the attribute head, not an incidental noun in a benefit/service:
    # 'refunds of tuition fees' has head refunds, not fees; 'fixed-rate
    # coverage' has head coverage, not rate. 'Emergency care information'
    # instead has the informational head information.
    noun_phrase = re.split(r"\s+(?:of|for|about|on|in|at|under)\s+", _clean(text), maxsplit=1, flags=re.I)[0]
    words = noun_phrase.split()
    return bool(words and (_INFORMATION.fullmatch(words[-1]) or noun_phrase.lower().endswith('notice period')))


def evidence_clauses(text):
    """Separate explicit contrast/additional clauses before granting exemptions."""
    return [part for part in _CLAUSE.split(text) if _clean(part)]


def _omission(text):
    match = _NEGATED_VERB.match(_core(text))
    if not match or not _DOC_SUBJECT.fullmatch(match['subject']):
        return None
    # 'The policy does not provide emergency care' is a coverage fact, not
    # missing evidence. Representation verbs differ from provide/contain/include.
    if match['verb'].lower() in ('provide', 'give', 'contain', 'include') and not _information_object(match['object']):
        return None
    obj = re.sub(r"^(?:a|an|the|any)\s+", "", _clean(match['object']), flags=re.I).lower()
    return match['verb'].lower(), obj


def is_insufficiency_clause(text, cited_contents=()):
    """True only for evidence gaps, not every negative or 'does not provide'."""
    cited_contents = tuple(content for content in cited_contents if isinstance(content, str))
    core = _core(text)
    if _omission(core):
        return True
    if _FIRST_PERSON.match(core) or _FRAGMENT.match(core):
        return True
    if re.match(r"^(?:no|not enough|insufficient)\s+(?:information|evidence|details?)\b", core, re.I):
        return True
    no_information = re.match(r"^(?P<subject>.+?)\s+(?:provides?|gives?|contains?)\s+no\s+(?:information|evidence|details?)\b", core, re.I)
    if no_information and _DOC_SUBJECT.fullmatch(no_information['subject']):
        return True
    if re.match(r"^(?:there is|there's|there are)\s+(?:no|not enough|insufficient)\s+(?:information|evidence|details?)\b", core, re.I):
        return True
    passive = _PASSIVE_GAP.search(core)
    if _PASSIVE_REPORT.search(core) or (passive and (
            _information_object(core[:passive.start()]) or _DOC_LOCATION.search(core))):
        return True
    if re.match(r"^not (?:available|provided|stated|mentioned|specified)\b", core, re.I) and _DOC_LOCATION.search(core):
        return True

    # A cited literal negative fact wins over older broad phrase heuristics,
    # e.g. 'Parking is not available' or 'The product does not contain latex'.
    if any(core.lower() in _clean(content).lower() for content in cited_contents):
        return False
    if re.search(r"\bno (?:information|mention|details?|evidence)\b", core, re.I) and _DOC_LOCATION.search(core):
        return True

    # The saved response shifts 'policy' to the institution as subject. Only
    # align a matching omitted object in that sentence's actual cited sources.
    match = _NEGATED_VERB.match(core)
    if match:
        obj = re.sub(r"^(?:a|an|the|any)\s+", "", _clean(match['object']), flags=re.I).lower()
        wanted = (match['verb'].lower(), obj)
        for content in cited_contents:
            for sentence in re.split(r"(?<=[.!?])\s+|\n+", content):
                for clause in evidence_clauses(sentence):
                    if _omission(clause) == wanted:
                        return True
    return False
