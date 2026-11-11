import re

# D1 design rule: a message is a memory-deletion request ONLY when the user
# clearly tells the application to forget / delete / erase / remove / clear
# something in ITS stored memory about the user. Every pattern therefore needs
# a personal stored-memory subject ("what you remember about me", "my saved
# memories", "the memory about my ...", "my <personal thing>", "what I told
# you"). Generic verb + the word "memory" is deliberately NOT enough (it also
# means RAM, caches, memory leaks, ...). False negatives are preferred over
# accidental deletion: any ambiguous message returns False.

_VERB = r"(?:forget|delete|remove|erase|clear|wipe)"
# Politeness prefixes are skipped by a short linear loop (see _skip_prefix) instead of a
# repeated group inside every pattern, so input such as "please " * 100000 cannot make
# the regex engine backtrack. The patterns below are matched at the position after the prefix.
_FORGET_PREFIX = re.compile(
    r"(?:please|kindly|can you|could you|would you|will you|"
    r"i want you to|i['’]?d like you to|i need you to)[ ,]+"
)
_DONT_PREFIX = re.compile(r"(?:please|kindly|can you|could you)[ ,]+")
_POLITE_FORGET = ""
_POLITE_DONT = ""
_QUANT = r"(?:all |any |every |all of |any of )?"
_STORED = r"(?:(?:saved|stored|previous|old|personal|earlier) )*"
_TOLD = r"(?:told|shared|said|mentioned|gave|have told|have shared|have said)"

# Subject is explicit: stored memory about the user.
EXPLICIT_PATTERNS = [
    # "Forget what you remember about me", "forget everything you know about me"
    _POLITE_FORGET + _VERB + r" (?:about )?(?:everything|all|anything|whatever|what) "
    r"(?:that )?you(?: (?:remember|know)| (?:have )?(?:stored|saved|remembered)|"
    r"['’]ve (?:stored|saved|remembered)) about me\b",
    # "Delete my saved memories", "Clear my memories", "delete your stored memory"
    _POLITE_FORGET + _VERB + r" " + _QUANT + r"(?:my|your) " + _STORED + r"memories\b",
    _POLITE_FORGET + _VERB + r" " + _QUANT + r"(?:my|your) " + _STORED
    + r"memory(?! (?:leak|usage|cache|address|allocation|error|management|variable|"
    r"footprint|dump|limit|size)\b)\b",
    # "Delete the saved/stored memories"
    _POLITE_FORGET + _VERB + r" " + _QUANT + r"(?:the )?(?:saved|stored) memories\b",
    # "Clear all memories you have stored about me"
    _POLITE_FORGET + _VERB + r" " + _QUANT + r"(?:the |my |your )?" + _STORED
    + r"memories (?:(?:that )?you(?: have|['’]ve)? (?:stored|saved|kept) )?(?:about|of) me\b",
    # "Remove the memory about my old project", "delete this memory about me"
    _POLITE_FORGET + _VERB + r" (?:the |this |that )memory (?:about|of|regarding) "
    r"(?:my|me|what i|the fact)\b",
    # "Delete this memory from your stored memories."
    _POLITE_FORGET + _VERB + r" (?:the |this |that )memory from your " + _STORED
    + r"(?:memory|memories)\b",
    # "Forget what I told you", "forget the personal details I shared earlier"
    _POLITE_FORGET + r"forget (?:what|(?:the |all the |all my |my )?" + _STORED
    + r"(?:details|information|info|facts?|things|stuff)) (?:that )?i " + _TOLD + r"\b",
    _POLITE_FORGET + r"forget the fact that i\b",
    _POLITE_FORGET + r"forget that i (?:use|like|live|work|prefer|have|am|was|study)\b",
    # "Forget me"
    _POLITE_FORGET + r"forget (?:about )?me$",
    _POLITE_FORGET + r"forget everything (?:you (?:know|remember) )?about me\b",
]

# Personal-information nouns: "forget my <one of these>" is a deletion request on its
# own; other possessions/tasks/activities ("my homework", "my project", "my code")
# are NOT, unless the sentence also names the stored memory (see below).
_MODS = r"(?:[\w'’-]+ ){0,2}"
_PERSONAL = (
    r"(?:phone(?: number)?|number|address|e-?mail(?: address)?|"
    r"password|age|birthday|location|city|details|info|information|preferences?|habits?|"
    r"hobb(?:y|ies)|job|family|interests?|diet|religion|nationality|favou?rite \w+)"
)
# "name" is accepted only bare or as first/last/full/real name (not "variable name").
_NOUN_PHRASE = r"(?:(?:first |last |full |real )?name|" + _MODS + _PERSONAL + r")\b"
_SAVED = r"(?:saved |stored )*"

# Subject is the user's personal information, or the sentence names the stored memory.
WEAK_PATTERNS = [   # matched after the forget-prefix
    # "Forget my phone number", "Forget my previous job details", "Please forget my cricket habit"
    _POLITE_FORGET + r"forget my " + _NOUN_PHRASE,
    # Stored-memory context named in the sentence:
    # "Forget my Python learning goals from your saved memory", "Forget my phone number from your memory"
    _POLITE_FORGET + _VERB + r" my [^.,;:!?]{1,60}? from your " + _SAVED + r"(?:memory|memories)\b",
    # "Remove my preference from memory." (bare "from memory" needs a personal-information noun)
    _POLITE_FORGET + _VERB + r" my " + _NOUN_PHRASE + r" from " + _SAVED + r"(?:memory|memories)\b",
    # "Delete the information you stored about my old project"
    _POLITE_FORGET + _VERB + r" (?:the |all the |all |any )?(?:information|info|details|facts?|data|"
    r"things|notes?) (?:that )?you(?: have|['’]ve)? (?:stored|saved|kept|remember|know) about (?:my|me)\b",
]

# "don't remember/keep/store/save <personal thing>" (matched after the don't-prefix)
DONT_PATTERNS = [
    _POLITE_DONT + r"(?:don['’]?t|do not) (?:remember|keep|store|save) "
    r"(?:my (?:name|phone|number|address|email|password|age|birthday|location|city|details|"
    r"info|information|preferences?|habits?|hobbies|hobby|job|family|favou?rites?)\b|"
    r"what i (?:said|told|shared)|anything about me|things about me|"
    r"(?:my )?personal (?:details|information|info))",
]

# "stop remembering ..." may appear anywhere in the sentence (unanchored, no repetition)
ANYWHERE_PATTERNS = [
    r"\bstop remembering (?:my " + _NOUN_PHRASE + r"|me\b|what i\b|that i\b|"
    r"things about me|anything about me|everything about me)",
]

FORGET_PATTERNS = EXPLICIT_PATTERNS + WEAK_PATTERNS + DONT_PATTERNS + ANYWHERE_PATTERNS
_EXPLICIT = [re.compile(p) for p in EXPLICIT_PATTERNS]
_WEAK = [re.compile(p) for p in WEAK_PATTERNS]
_DONT = [re.compile(p) for p in DONT_PATTERNS]
_ANYWHERE = [re.compile(p) for p in ANYWHERE_PATTERNS]


def _skip_prefix(message, prefix):
    """Position after any number of leading politeness phrases (linear time)."""
    pos = 0
    while True:
        match = prefix.match(message, pos)
        if not match:
            return pos
        pos = match.end()


def is_explicit_memory_delete_request(message: str) -> bool:
    # D6: only real strings can be a request. Other types (None, numbers, bool,
    # list, dict, bytes, ...) are never converted to text and never match.
    if not isinstance(message, str) or not message:
        return False

    message = re.sub(r"\s+", " ", message.lower().strip()).rstrip(" .!?,;")

    start = _skip_prefix(message, _FORGET_PREFIX)
    if any(p.match(message, start) for p in _EXPLICIT):
        return True
    if any(p.match(message, start) for p in _WEAK):
        return True

    start = _skip_prefix(message, _DONT_PREFIX)
    if any(p.match(message, start) for p in _DONT):
        return True

    return any(p.search(message) for p in _ANYWHERE)
