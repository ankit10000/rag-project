# D1 fix report — false-positive memory-deletion detection

Date: 2026-11-11. Scope: defect D1 only (D3–D7 untouched; classifier, storage, ownership, cleanup and the D2 fix unchanged). Nothing committed. No live Gemini (network blocked for every run). `rag_db` untouched.

## Design rule
A message is a deletion request only when the user clearly tells the app to forget/delete/erase/remove/clear something **in its stored memory about the user**. Every pattern needs a personal stored-memory subject. Generic verb + the word "memory" is no longer enough. Ambiguous → `False` (false negatives preferred). Interface unchanged: `is_explicit_memory_delete_request(message) -> bool`, regex only, no Gemini.

## Detector before → after (`services/memory_delete_service.py`, the only application file changed)
**Before** (4 broad patterns): `forget|erase` + `my|me|everything|all|what i|the fact|our`; any `stop remembering`; `don't remember/keep/store/save` … `my|me|this|that|it`; and `delete|remove|erase|clear|wipe` … `memory|memories` anywhere in the sentence.

**After**
- *Explicit patterns* (anchored at the start, optional "please/can you/I want you to…"): "forget what/everything you remember/know/(have) stored about me"; verb + "my/your (saved/stored…) memories" or "my/your memory" (not followed by leak/usage/cache/…); verb + "the saved/stored memories"; verb + "(all) memories (you have stored) about me"; verb + "the/this memory about my/me/…"; verb + "this memory from your stored memories"; "forget what I told you", "forget the (personal) details/information I shared", "forget the fact that I…", "forget that I use/live/…", "forget me", "forget everything about me".
- *Weak patterns* (only when no technical word such as python, react, cache, pdf, file, code, memory, …): "forget my <something>", "stop remembering my/me/what I…", "don't remember/keep/store/save" + a personal noun (name, phone, address, password, preferences, details, …) or "what I told you / anything about me".
- Trailing `. ! ? , ;` stripped; `’` and `'` both handled; no nested/unbounded `.*` (anchored, linear).

## Behaviour changes that are deliberate (false negatives now)
Previously True, now False because they lack a clear personal stored-memory subject: `Forget everything`, `please erase all`, `Erase everything`, `Erase my preferences`, `Forget about my project`, `forget our plan`, `Forget all the tests I wrote`, `please stop remembering`, `Please don't store this`, `do not keep it`, `Don't save that`, `Delete this memory`, `erase this memory`, `delete memory`, `Wipe all memories`, `Remove the memory about X`, `Remove my preference from memory.`. All are re-pinned in the test with the rationale. Existing valid commands that meet the rule are unchanged (e.g. `Forget my Hinglish preference`, `Please forget my cricket habit`, `stop remembering my cricket habit`, `Don't remember my phone number`, `Delete this memory from your stored memories.`, `Clear my memories`, `forget what I told you`).

## Changed files
- `services/memory_delete_service.py` (rewritten detector)
- `test_memory_delete_detector.py` (D1 pins, 6 spec positives, 11 spec negatives, ~24 positive variations, ~55 negative cases across Python/JS/React/OS/DB/cache and other uses of forget/save/remove; the 7 audit false-positive probes are now assertions; D6 probes P-B/P-C left as probes)
- `test_p1_delete_routing.py` (3 FINDING probes → assertions that these go to RAG; 9 negatives take the RAG path; 6 spec positives reach `delete_matching_memories` with the exact request)

## Results (executed)
| File | PASS | FAIL | FINDING lines |
|---|---|---|---|
| `test_memory_delete_detector.py` | 180 | 0 | 3 (D6 non-str probes, out of scope) |
| `test_p1_decision_parsing.py` | 110 | 0 | 5 |
| `test_p1_process_memory.py` | 104 | 0 | 0 |
| `test_p1_memory_update_delete_integration.py` | 37 | 0 | 1 |
| `test_p1_delete_routing.py` | 136 | 0 | 0 (was 3) |
| `test_p1_cleanup_failure.py` | 54 | 0 | 0 |

Full default suite (`run_tests.py --clean`): **19 / 19 passed, 0 failed**, including the D2 test (43 checks); `rag_db` fingerprint unchanged: True.

## Mutation checks (repo not edited; mutations injected in memory)
| Mutation | Test | Result |
|---|---|---|
| detector never matches | detector test | caught: exit 1, 57 FAIL |
| detector matches everything | detector test | caught: exit 1, 118 FAIL |
| old broad detector restored | detector test | caught: exit 1, 71 FAIL |
| old broad detector restored | routing test | caught: exit 1, 12 FAIL |
| detector never matches / routing detector off | routing test | caught: exit 1, 17 FAIL each |
| routing detector always True | routing test | caught: exit 1 (run aborts with an exception at an early check; 0 assertion FAILs printed) |

## Database safety
- `rag_db` counts unchanged by the runner fingerprint (conversations, messages, memories, links, chunks); all tests used `rag_test_scratch`, network blocked; scratch emptied by `--clean`.
- No migration, no commit, no `.env` output.

## Remaining ambiguous / known cases
- Bare commands now intentionally ignored: "Forget everything", "Delete this memory", "Forget about my project". The user must name their stored memory or a personal thing ("forget my …").
- "Forget my <technical thing>" (e.g. "Forget my Python learning goals") is ignored because of the technical veto — a false negative by design.
- "Forget my <non-memory thing>" such as "Forget my homework" still counts as a deletion request (it is a command about the user's own item; the classifier then decides, and D2 prevents deleting on an unclear answer).
- Detector only handles English; Hinglish phrasings beyond "forget my …" are not detected.
- D6 (non-str input raises; this report did not touch it) remains.

---

# Correction round (after review)

Scope: D1 only. Files changed: `services/memory_delete_service.py`, `test_memory_delete_detector.py`, `test_p1_delete_routing.py`. D2 fix, classifier, storage, ownership and cleanup untouched.

## 1. Technical-word veto removed
The blanket veto (python, react, cache, file, … anywhere in the sentence) is gone. Decisions now come from sentence structure and subject:
- **Personal-information noun** after "forget my …": name (bare/first/last/full/real), phone (number), address, email, password, age, birthday, location, city, details, info(rmation), preference(s), habit(s), hobby, job, family, interests, diet, religion, nationality, "favourite X". Up to two modifiers are allowed ("previous job details", "cricket habit").
- **Stored-memory context named in the sentence**: "<verb> my … from your (saved/stored) memory/memories" (any subject), "<verb> my <personal noun> from memory", "<verb> the information/details you stored about my/me", plus all earlier explicit patterns.
- Generic "memory" + verb, or technical wording without a personal-memory subject, never matches.

## 2. Non-memory subjects
"Forget my homework / assignment / project / tasks / code / cricket match / exam schedule" → no longer detected. "Stop remembering my homework" and "Don't save my homework" → not detected. "Forget my variable name" → not detected (name only bare or first/last/full/real).
Routing test query changed from "Forget my RAG project" to "Forget my cricket habit" (the old query is no longer a deletion request by design).

## 3. Explicit coverage added (all assertions, all pass)
Detected: "Remove my preference from memory.", "Forget my phone number", "Forget my phone number from your memory.", "Forget my Python learning goals from your saved memory.", "Delete the information you stored about my old project.", "Forget my JavaScript experience level from your stored memories", "Please forget my Python preferences", "Remove my email address from your memory", "Can you remove my job details from memory?", …
Not detected (kept/extended): "Forget my Python learning goals" (alone), "How do I clear memory in Python?", "Fix the memory leak in my React code", "Delete memory from the cache", "Remove my array/variable/file from memory", "Clear my python variable from memory", OS/DB/cache/JS/React/Docker cases from the first round.

## 4. Routing mutation test
Added an explicit assertion early ("What is RAG?" never enters the deletion flow) and made `call_args` accesses non-raising (`last()` helper, `.get`). The detector-always-True mutation now fails through assertions, no traceback.

## Evidence
| Run | Result |
|---|---|
| `test_memory_delete_detector.py` | 213 PASS, 0 FAIL (3 FINDING lines = D6 non-str probes, out of scope) |
| `test_p1_delete_routing.py` | 137 PASS, 0 FAIL, 0 FINDING |
| other four Cycle 1 files | 110 / 104 / 37 / 54 PASS, 0 FAIL |
| Mutation: detector never matches | detector test 70 FAIL |
| Mutation: detector matches everything | detector test 138 FAIL |
| Mutation: old broad detector | detector test 86 FAIL; routing test 12 FAIL |
| Mutation: routing detector always True | routing test **33 FAIL, 0 tracebacks** |

Full default suite and `rag_db` fingerprint: see final line below.

## Changed pins
"Remove my preference from memory." flips back to **True** (original behaviour restored). Everything else from the first-round false-negative list is unchanged.

## Remaining edge cases
- "Forget my React project details" is detected (personal-noun "details" with modifiers); the classifier and D2 still gate the actual deletion.
- "Forget my <non-listed personal thing>" (e.g. "Forget my goals") is not detected unless it names your memory.
- English only; D6 (non-str input) untouched.

Final: full default suite (`run_tests.py --clean`) **19 / 19 passed, 0 failed**; application database `rag_db` fingerprint unchanged: **True**.
