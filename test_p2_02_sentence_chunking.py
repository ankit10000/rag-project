"""P2-02: sentence-based chunking verification (services/chunker.py).

Pure-function tests of split_sentences / chunk_text_sentences / chunk_page, the unchanged word
strategy, and one scratch-DB check that ingestion honours CHUNK_STRATEGY=sentences with
deterministic chunk ids (deterministic substitute embedder; no model output is asserted).

Existing behaviour that is UNDEFINED or limited is PINNED here as "current behaviour" and
documented in docs/remediation/P2_02_SENTENCE_CHUNKING_REPORT.md; it is not a requirement.
"""
import testsafe  # refuses to run against anything but a scratch database
testsafe.require_scratch_db()

import contextlib
import io
import os
import random
import shutil
import sys
import tempfile
import uuid
from unittest import mock

import numpy as np
import pymupdf

import services.ingestion_service as ingestion
from services import retrieval_config as cfg
from services.chunker import chunk_page, chunk_text, chunk_text_sentences, split_sentences
from services.database import get_connection

FAILURES = []
PREFIX = "p2_02_"
WORKDIR = tempfile.mkdtemp(prefix="p2_02_pdf_")


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


def raises(fn, exc=ValueError):
    try:
        fn()
    except exc:
        return True
    except Exception:  # noqa: BLE001
        return False
    return False


def sent(n, w, tag="T"):
    """Sentence number n with exactly w words; starts with a capital so it is a valid boundary."""
    first = f"S{tag}{n}x0"
    return first + "".join(f" {tag}{n}w{i}" for i in range(1, w)) + "."


def wc(chunk):
    return len(chunk.split())


# --------------------------------------------------------------------------------------
# split_sentences: boundary rules (current behaviour)
# --------------------------------------------------------------------------------------
check("[split] empty / whitespace-only -> []",
      split_sentences("") == [] and split_sentences("   ") == [] and split_sentences("\n\n \t\n") == [])
check("[split] period, question mark and exclamation mark followed by a capital are boundaries",
      split_sentences("It works. Does it work? It works! Yes.") == ["It works.", "Does it work?", "It works!", "Yes."])
check("[split] a digit, quote or parenthesis after the space also starts a new sentence",
      split_sentences('First one. 2nd one. "Quoted" next. (Paren) last.') ==
      ["First one.", "2nd one.", '"Quoted" next.', "(Paren) last."])
check("[split] lowercase continuation is NOT a boundary (e.g. 'e.g. this')",
      split_sentences("Use tools, e.g. a hammer. Then rest.") == ["Use tools, e.g. a hammer.", "Then rest."])
check("[split] decimal numbers are not boundaries",
      split_sentences("Pi is 3.14 and e is 2.718. Next sentence.") == ["Pi is 3.14 and e is 2.718.", "Next sentence."])
check("[split] version numbers / domains without a following space are not boundaries",
      split_sentences("See v2.0.1 or example.com today. Done.") == ["See v2.0.1 or example.com today.", "Done."])
check("[split, PINNED] abbreviation before a capital splits: 'Dr. Smith' -> two sentences",
      split_sentences("Dr. Smith arrived. He left.") == ["Dr.", "Smith arrived.", "He left."])
check("[split, PINNED] 'U.S. Army' splits after 'U.S.'", split_sentences("The U.S. Army won.") == ["The U.S.", "Army won."])
check("[split] lowercase abbreviation use does not split ('etc. and more')",
      split_sentences("Apples, pears, etc. and more fruit. End.") == ["Apples, pears, etc. and more fruit.", "End."])
check("[split] text without terminal punctuation is one sentence", split_sentences("no punctuation at all") == ["no punctuation at all"])
check("[split] blank line separates paragraphs even without punctuation",
      split_sentences("Heading line\n\nBody starts here. Second one.") == ["Heading line", "Body starts here.", "Second one."])
check("[split] single newline inside a paragraph is treated as a space",
      split_sentences("Line one\ncontinues here. Next.") == ["Line one continues here.", "Next."])
check("[split] repeated whitespace/tabs/newlines collapse; leading/trailing whitespace dropped",
      split_sentences("  Hello    there.\t\tGeneral   Kenobi!  \n\n  ") == ["Hello there.", "General Kenobi!"])
check("[split] CRLF line endings behave like LF",
      split_sentences("Para one. Two.\r\n\r\nPara two.") == ["Para one.", "Two.", "Para two."])
check("[split] unicode (accents, CJK, emoji) is kept intact inside sentences; an ASCII '.' + capital still splits",
      split_sentences("Café crème est bon. Emoji 😀 ok. 日本語のテスト。") ==
      ["Café crème est bon.", "Emoji 😀 ok. 日本語のテスト。"])
check("[split, PINNED] a sentence that starts with a non-ASCII letter (CJK/accented) is not split off after '.'",
      split_sentences("Done. École next. Fin.") == ["Done. École next.", "Fin."])
check("[split, PINNED] only ASCII capitals/digits start a sentence: Cyrillic capital after '.' does not split",
      split_sentences("Привет мир. Это тест.") ==
      ["Привет мир. Это тест."])
check("[split, PINNED] the Devanagari danda (।) is not a sentence terminator",
      len(split_sentences("यह एक वाक्य है। अगला वाक्य.")) == 1)
check("[split] ellipsis followed by a capital splits ('Wait... Then')", split_sentences("Wait... Then go.") == ["Wait...", "Then go."])

# --------------------------------------------------------------------------------------
# chunk_text_sentences: basic shapes
# --------------------------------------------------------------------------------------
check("[sent] empty / whitespace-only -> []",
      chunk_text_sentences("", 100, 20) == [] and chunk_text_sentences("  \n\t \n\n", 100, 20) == [])
check("[sent] one short sentence -> one chunk equal to the (whitespace-normalised) sentence",
      chunk_text_sentences("  Just   one\nsentence here.  ", 100, 20) == ["Just one sentence here."])
check("[sent] text without any punctuation within size -> one chunk",
      chunk_text_sentences("alpha beta gamma", 100, 20) == ["alpha beta gamma"])
two = chunk_text_sentences("First sentence here. Second one follows.", 100, 20)
check("[sent] several sentences within chunk_size are packed into one chunk, single-space joined",
      two == ["First sentence here. Second one follows."])
para = chunk_text_sentences("Para one sentence. Still one.\n\nPara two sentence.", 100, 20)
check("[sent, PINNED] paragraphs are merged into one chunk when they fit (paragraph breaks are not preserved)",
      para == ["Para one sentence. Still one. Para two sentence."])
check("[sent] question/exclamation sentences are packed like any other",
      chunk_text_sentences("Is it? Yes! Good.", 100, 20) == ["Is it? Yes! Good."])

# --------------------------------------------------------------------------------------
# size, overlap, ordering, content (hand-built, exact expectations)
# --------------------------------------------------------------------------------------
S = [sent(i, 10) for i in range(1, 31)]   # 30 sentences x 10 words
text30 = " ".join(S)

c = chunk_text_sentences(text30, 50, 0)
check("[size] chunk_size=50, overlap=0 -> chunks of exactly 5 sentences, partitioning the text",
      [wc(x) for x in c] == [50] * 6 and " ".join(c) == text30)
check("[size] every chunk starts at a sentence start and ends at a sentence end (no mid-sentence cuts)",
      all(x.split()[0].startswith("ST") and x.endswith(".") for x in c))

c = chunk_text_sentences(text30, 50, 10)
check("[overlap] chunk_size=50, overlap=10: next chunk starts with the last sentence of the previous one",
      all(c[i + 1].split()[0] == c[i].split()[-10] for i in range(len(c) - 1)))
check("[overlap] overlap=10 -> chunk word counts [50,50,50,50,50,50,50,20]", [wc(x) for x in c] == [50] * 7 + [20])
check("[overlap] consecutive chunks share exactly the last 10 words (one sentence)",
      all(c[i].split()[-10:] == c[i + 1].split()[:10] for i in range(len(c) - 1)))

c = chunk_text_sentences(text30, 100, 20)
check("[overlap] overlap=20 -> two whole sentences (20 words) are carried into the next chunk",
      [wc(x) for x in c] == [100, 100, 100, 60]
      and all(c[i].split()[-20:] == c[i + 1].split()[:20] for i in range(len(c) - 1)))

c = chunk_text_sentences(text30, 100, 19)
check("[overlap] overlap budget smaller than two sentences (19) carries only one sentence",
      all(c[i].split()[-10:] == c[i + 1].split()[:10] and c[i].split()[-11] != c[i + 1].split()[0] for i in range(len(c) - 1)))

c = chunk_text_sentences(text30, 50, 9)
check("[overlap] overlap smaller than every sentence (9 < 10) -> no overlap at all, exact partition",
      " ".join(c) == text30)

c = chunk_text_sentences(text30, 50, 49)
check("[overlap] overlap = chunk_size-1 is accepted; output stays within size and keeps all content",
      all(wc(x) <= 50 for x in c) and set(" ".join(c).split()) == set(text30.split()))

# ordering + content preservation
c = chunk_text_sentences(text30, 50, 10)
firsts = [S.index(next(s for s in S if s.startswith(x.split()[0]))) for x in c]
check("[order] chunks follow source order (first sentence index strictly increases)", firsts == sorted(set(firsts)))
check("[content] every word of the input appears in some chunk, none invented",
      set(" ".join(c).split()) == set(text30.split()))
check("[content] last chunk ends with the last input word", c[-1].split()[-1] == text30.split()[-1])
check("[content] with overlap 0 the concatenation reproduces the normalised text exactly",
      " ".join(chunk_text_sentences(text30, 30, 0)) == text30)
check("[determinism] repeated calls give identical output", chunk_text_sentences(text30, 50, 10) == c)
check("[no empty chunks] no empty or whitespace-only chunk", all(x.strip() for x in c))

# chunk-size cap: the defect found in P2-02 (carry + new sentence used to exceed chunk_size)
cap = chunk_text_sentences(" ".join([sent(1, 60), sent(2, 10), sent(3, 10), sent(4, 95)]), 100, 20)
check("[size cap] overlap carry never pushes a chunk past chunk_size ([80, 95]; was [80, 115] before the fix)",
      [wc(x) for x in cap] == [80, 95])
check("[size cap] the oversize-avoiding chunk keeps all content",
      set(" ".join(cap).split()) == set(" ".join([sent(1, 60), sent(2, 10), sent(3, 10), sent(4, 95)]).split()))

# long sentences
long1 = sent(1, 250)
c = chunk_text_sentences(long1, 100, 20)
check("[long] a single 250-word sentence is split by words into windows of <=100 with 20-word overlap",
      [wc(x) for x in c] == [100, 100, 90]
      and c[0].split()[-20:] == c[1].split()[:20] and c[1].split()[-20:] == c[2].split()[:20]
      and " ".join(long1.split()) == " ".join(c[0].split()[:80] + c[1].split()[:80] + c[2].split()))
c = chunk_text_sentences(" ".join([sent(1, 5), long1, sent(3, 5)]), 100, 20)
check("[long] short - long - short: nothing exceeds chunk_size, order and content kept",
      all(wc(x) <= 100 for x in c) and c[0].startswith("ST1x0") and c[-1].endswith("T3w4.")
      and set(" ".join(c).split()) == set(" ".join([sent(1, 5), long1, sent(3, 5)]).split()))
two_long = " ".join([sent(1, 130), sent(2, 130)])
c = chunk_text_sentences(two_long, 100, 20)
check("[long] multiple long sentences: every chunk <= chunk_size, windows never mix the two sentences' tail in a way "
      "that loses words",
      all(wc(x) <= 100 for x in c) and set(" ".join(c).split()) == set(two_long.split()))
check("[long, defect fixed] no trailing window that only repeats words already covered "
      "(250 words -> [100, 100, 90]; was [100, 100, 100] with the last 10 words twice)",
      all(len(set(x.split())) == len(x.split()) for x in chunk_text_sentences(long1, 100, 20)))
check("[long] sentence of exactly chunk_size words stays whole",
      chunk_text_sentences(sent(1, 100), 100, 20) == [sent(1, 100)])
check("[long] sentence of chunk_size+1 words is split", len(chunk_text_sentences(sent(1, 101), 100, 20)) == 2)

# configuration validation
check("[config] chunk_size <= 0 -> ValueError (sentences and words)",
      raises(lambda: chunk_text_sentences("a b.", 0, 0)) and raises(lambda: chunk_text_sentences("a b.", -5, 0))
      and raises(lambda: chunk_text("a b", 0, 0)) and raises(lambda: chunk_text("a b", -5, 0)))
check("[config] negative overlap -> ValueError", raises(lambda: chunk_text_sentences("a b.", 10, -1)) and raises(lambda: chunk_text("a b", 10, -1)))
check("[config] overlap == chunk_size and overlap > chunk_size -> ValueError",
      raises(lambda: chunk_text_sentences("a b.", 10, 10)) and raises(lambda: chunk_text_sentences("a b.", 10, 11))
      and raises(lambda: chunk_text("a b", 10, 10)) and raises(lambda: chunk_text("a b", 10, 11)))
check("[config] validation happens even for empty text", raises(lambda: chunk_text_sentences("", 0, 0)))
check("[config] chunk_size=1, overlap=0 works: one word per chunk",
      chunk_text_sentences("Alpha beta. Gamma delta.", 1, 0) == ["Alpha", "beta.", "Gamma", "delta."])

# unicode through the chunker
uni = "Café crème über naïve. 日本語 テスト \U0001F600. Last one here."
check("[unicode] accented/CJK/emoji words survive chunking unchanged",
      " ".join(chunk_text_sentences(uni, 100, 20)).split() == uni.split())

# --------------------------------------------------------------------------------------
# word strategy: unchanged by P2-02, and dispatch
# --------------------------------------------------------------------------------------
w250 = " ".join(f"w{i}" for i in range(250))
wch = chunk_text(w250, 100, 20)
check("[words, unchanged] 250 words, 100/20 -> chunks of 100, 100, 90 starting at words 0, 80, 160",
      [wc(x) for x in wch] == [100, 100, 90] and [x.split()[0] for x in wch] == ["w0", "w80", "w160"])
check("[words, unchanged] empty / whitespace -> []", chunk_text("", 100, 20) == [] and chunk_text("  \n", 100, 20) == [])
check("[words, unchanged] short text -> one chunk; whitespace normalised", chunk_text(" a   b\nc ", 100, 20) == ["a b c"])
check("[words, unchanged] never exceeds chunk_size", all(wc(x) <= 100 for x in chunk_text(w250, 100, 99)))
check("[dispatch] strategy 'words' == chunk_text; 'sentences' == chunk_text_sentences",
      chunk_page(text30, 50, 10, "words") == chunk_text(text30, 50, 10)
      and chunk_page(text30, 50, 10, "sentences") == chunk_text_sentences(text30, 50, 10))
check("[dispatch] default strategy is 'words'; unknown strategy falls back to words (current behaviour)",
      chunk_page(text30, 50, 10) == chunk_text(text30, 50, 10) and chunk_page(text30, 50, 10, "bogus") == chunk_text(text30, 50, 10))
diff_text = " ".join([sent(1, 60), sent(2, 60), sent(3, 60)])
check("[dispatch] word and sentence strategies are independent (different output on suitable text, each stable "
      "after the other ran)",
      chunk_text(diff_text, 100, 20) != chunk_text_sentences(diff_text, 100, 20)
      and chunk_text(diff_text, 100, 20) == chunk_page(diff_text, 100, 20, "words")
      and chunk_text_sentences(diff_text, 100, 20) == chunk_page(diff_text, 100, 20, "sentences"))

# --------------------------------------------------------------------------------------
# randomised invariants (fixed seed -> deterministic)
# --------------------------------------------------------------------------------------
rng = random.Random(20261112)
broken = {"repeated_words_in_chunk": 0, "empty": 0, "oversize": 0, "lost": 0, "order": 0, "nondeterministic": 0, "invented": 0}
trials = 600
for _ in range(trials):
    size = rng.choice([3, 5, 10, 25, 50, 100])
    ov = rng.randrange(0, size)
    sents = [sent(i, rng.choice([1, 2, 3, 5, 8, 12, 20, 40, 70, 130])) for i in range(rng.randrange(1, 15))]
    text = " ".join(sents)
    chunks = chunk_text_sentences(text, size, ov)
    if chunks != chunk_text_sentences(text, size, ov):
        broken["nondeterministic"] += 1
    if not chunks or any(not x.strip() for x in chunks):
        broken["empty"] += 1
    if any(wc(x) > size for x in chunks):
        broken["oversize"] += 1
    if any(len(set(x.split())) != len(x.split()) for x in chunks):
        broken["repeated_words_in_chunk"] += 1
    src, got = text.split(), " ".join(chunks).split()
    if set(src) != set(got):
        broken["lost"] += 1
    if not set(got) <= set(src):
        broken["invented"] += 1
    position = {w: i for i, w in enumerate(src)}
    starts = [position[x.split()[0]] for x in chunks]
    if starts != sorted(starts):
        broken["order"] += 1
check(f"[random x{trials}] no empty chunks, no chunk above chunk_size, no lost or invented words, source order, deterministic "
      f"({broken})", all(v == 0 for v in broken.values()))


# --------------------------------------------------------------------------------------
# ingestion honours CHUNK_STRATEGY=sentences, deterministic chunk ids (scratch DB)
# --------------------------------------------------------------------------------------
def make_pdf(name, pages):
    path = os.path.join(WORKDIR, name)
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            rc = page.insert_textbox(pymupdf.Rect(40, 40, 555, 800), text, fontsize=9)
            assert rc >= 0, "test PDF text did not fit"
    doc.save(path)
    doc.close()
    return path


def rows_for(name):
    with get_connection() as conn:
        return conn.execute("SELECT page_number, chunk_id, content, vector_dims(embedding) FROM document_chunks "
                            "WHERE document_name=%s ORDER BY page_number, chunk_id", (name,)).fetchall()


def fixed_embedder(texts):
    vector = np.zeros(cfg.EMBEDDING_DIM)
    vector[3] = 1.0
    return np.tile(vector, (len(texts), 1))


def ingestion_checks():
    with get_connection() as conn:
        baseline = conn.execute("SELECT count(*) FROM document_chunks WHERE document_name NOT LIKE %s",
                                (PREFIX + "%",)).fetchone()[0]
    page1 = " ".join(sent(i, 12, "A") for i in range(1, 21))       # 20 sentences x 12 words = 240 words
    page2 = " ".join(sent(i, 12, "B") for i in range(1, 11))       # 120 words
    name = f"{PREFIX}{uuid.uuid4().hex[:10]}.pdf"
    pdf = make_pdf(name, [page1, page2])
    expected = {1: chunk_text_sentences(page1, cfg.CHUNK_SIZE, cfg.CHUNK_OVERLAP),
                2: chunk_text_sentences(page2, cfg.CHUNK_SIZE, cfg.CHUNK_OVERLAP)}
    with mock.patch.object(cfg, "CHUNK_STRATEGY", "sentences"), \
            mock.patch.object(ingestion, "generate_embeddings", side_effect=fixed_embedder), \
            contextlib.redirect_stdout(io.StringIO()):
        ingestion.ingest_pdf(pdf)
        rows = rows_for(name)
        ingestion.ingest_pdf(pdf)
        again = rows_for(name)
    want = [(p, i, text) for p in (1, 2) for i, text in enumerate(expected[p], start=1)]
    check("[ingest, strategy=sentences, DETERMINISTIC embedder] stored rows == sentence chunks, chunk ids 1..n per page",
          [(r[0], r[1], r[2]) for r in rows] == want and len(want) >= 4)
    check("[ingest, strategy=sentences] every stored chunk is within chunk_size and ends on a sentence end",
          all(wc(r[2]) <= cfg.CHUNK_SIZE and r[2].endswith(".") for r in rows))
    check("[ingest, strategy=sentences] vectors have the configured dimension", all(r[3] == cfg.EMBEDDING_DIM for r in rows))
    check("[ingest, strategy=sentences] chunk ids deterministic: re-ingestion gives the same rows, no extras", again == rows)
    with mock.patch.object(ingestion, "generate_embeddings", side_effect=fixed_embedder), \
            contextlib.redirect_stdout(io.StringIO()):
        other = f"{PREFIX}{uuid.uuid4().hex[:10]}.pdf"
        ingestion.ingest_pdf(make_pdf(other, [page1]))
        word_rows = rows_for(other)
    check("[ingest, default strategy] the default (words) strategy is unchanged: rows == chunk_text chunks",
          cfg.CHUNK_STRATEGY == "words"
          and [r[2] for r in word_rows] == chunk_text(page1, cfg.CHUNK_SIZE, cfg.CHUNK_OVERLAP))
    with get_connection() as conn:
        after = conn.execute("SELECT count(*) FROM document_chunks WHERE document_name NOT LIKE %s",
                             (PREFIX + "%",)).fetchone()[0]
    check("[isolation] rows of other documents unchanged", after == baseline)


try:
    ingestion_checks()
finally:
    with get_connection() as conn:
        conn.execute("DELETE FROM document_chunks WHERE document_name LIKE %s", (PREFIX + "%",))
    shutil.rmtree(WORKDIR, ignore_errors=True)

with get_connection() as conn:
    left = conn.execute("SELECT count(*) FROM document_chunks WHERE document_name LIKE %s", (PREFIX + "%",)).fetchone()[0]
check("[cleanup] no test rows left in document_chunks", left == 0)

if FAILURES:
    print("FAILED CHECKS: " + " ## ".join(FAILURES))
print(f"\n{len(FAILURES)} check(s) failed")
sys.exit(1 if FAILURES else 0)
