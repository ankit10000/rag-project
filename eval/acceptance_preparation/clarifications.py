"""Pure WP8 specification clarification evidence; no policy approval or scorer changes."""
import copy

SPEC='docs/remediation/phase_e2_engineering/wp5/SCORER_V2_1_SPEC.md'
REPORT='docs/remediation/phase_e2_engineering/WP6_IMPLEMENTATION_REPORT.md'
TEST='test_stage9_wp8_clarifications.py'
REGISTER_SCHEMA='phase35-wp8-specification-clarifications/1'
RESOLVED='RESOLVED_ENGINEERING'
PENDING='PENDING_OWNER_DECISION'


def _record(cid,title,section,line,original,behavior,paths,conflict,resolution,test,*,pending=False,proposal=''):
    return dict(id=cid,title=title,source=dict(path=SPEC,section=section,line=line,original_language=original if isinstance(original,list) else [original]),
        implementation=dict(behavior=behavior,paths=paths),
        evidence=dict(implementation_report=REPORT,report_section='Specification clarifications and traceability',
                      regression_test=TEST+'::'+test),
        conflict_or_ambiguity=conflict,resolution=resolution,
        resolution_status=PENDING if pending else RESOLVED,proposed_resolution=proposal,
        code_change_needed=False,code_change_scope='No existing WP6/WP7 source changes authorized or made in this workstream.',
        test_added=True,independent_review_required=True,review_status='NOT_REVIEWED',acceptance_approved=False)


_RECORDS=[
 _record('SC-01','Appendix B explicit probe outcomes','Appendix B',1212,
  '| P-TS1-06 (tier1) | True (residual) | **False** |',
  'P-TS1-06=False, P-TS1-08=False, P-TS4-10=False and P-E2-STAT-06=True; frozen v1 outcomes remain independent.',
  ['eval/probes/probes_phase_d.py','eval/probes/probes_e2.py','eval/scoring_v2/score.py'],
  'Earlier probe intents disagree with the authoritative superseding Appendix B table.',
  'Use Appendix B explicitly stated v2.1 values. This resolves engineering expectations, not acceptance of scoring policy.',
  'test_sc01_appendix_b_explicit_probe_values'),
 _record('SC-02','Plural relaxation is quantity-only','4.3',204,
  'If `n` has the form `<N> <word>` (one number token, one word), the right boundary also accepts `h` continuing with `s` or `es` and then a boundary',
  'Bare Tuesday does not match Tuesdays; bare filter does not match filters. Quantity 2 visitor matches 2 visitors.',
  ['eval/scoring_v2/normalize.py','eval/probes/probes_phase_d.py','eval/probes/probes_e2.py'],
  'Three historical v2 probe intents assumed a general plural rule absent from the closed specification.',
  'Apply the explicit quantity boundary rule; P-TS4-11, P-TA11-2 and P-E2-TA11-3 remain False. Do not add unreviewed gold alternatives.',
  'test_sc02_quantity_only_plural_boundary'),
 _record('SC-03','Preserve explicit quote glyph table before NFKC','4.1 M1/M2',122,
  ['`unicodedata.normalize("NFKC", s)`, then `casefold()`', '`’ ‘ ‛ ′` → `\'`; `“ ” „ ″` → `"`'],
  'Closed quote glyphs are translated before NFKC so U+2033 becomes one ASCII double quote.',
  ['eval/scoring_v2/normalize.py::light','eval/scoring_v2/tables.py::QUOTES'],
  'Literal M1-then-M2 loses double-prime identity: NFKC(U+2033) is two U+2032 characters, otherwise yielding two apostrophes.',
  'Honor the explicit M2 output table without widening its glyph set. This existing implementation precedence is tested; formal clarification acceptance remains independent.',
  'test_sc03_quote_map_survives_nfkc'),
 _record('SC-04','Number-word unit normalization must be idempotent','4.1 M12/M13 and 16.2',133,
  ['| M12 | Units |', '| M13 | Number words |', '`M` is idempotent;'],
  'Unit/currency normalization runs again after number-word conversion: twelve months becomes 12 month immediately.',
  ['eval/scoring_v2/normalize.py::M','eval/scoring_v2/normalize.py::_quantities'],
  'A single ordered pass creates 12 months on the first call and 12 month on the second, contradicting required idempotence.',
  'Satisfy the explicit idempotence acceptance property by completing existing closed quantity rules after number words; no new unit or word is introduced.',
  'test_sc04_number_word_quantity_idempotence'),
 _record('SC-05','AV-10 duplicates within collections, not across roles','13.3 example and AV-10',939,
  'No duplicate texts within a case',
  'Duplicate texts within forbidden or history_wrong_values are rejected; the same 2,000 may appear once in each collection.',
  ['eval/scoring_v2/annotations.py::entry_errors','eval/scoring_v2/annotations.py::validate_annotations'],
  'The exact section 13.3 example repeats 2,000 in forbidden and history_wrong_values, contradicting a whole-case ban.',
  'Use the explicit example to scope duplicate checking per collection. Full validation still checks actual history turn ownership, gold overlap and group bounds.',
  'test_sc05_full_sample_and_richer_annotations_valid'),
 _record('SC-06','Comma/but epistemic scope','6.1.5, 7.2 E and 7 residual',376,
  ['Commas **do not** split clauses.', 'every `V` **after** the end of that match, up to the end of the clause'],
  'Comma and but remain in one clause; family E can excuse a repeated Visa after but. A semicolon creates a separate asserted occurrence and fails.',
  ['eval/scoring_v2/text_units.py::split','eval/scoring_v2/negation.py::occurrence_family'],
  'Section 7 residual says a comma/but Visa repetition fails on its second clause, but the formal splitter does not create that clause.',
  'Unresolved: retain current experimental formal-grammar behavior, explicitly register its false-acceptance risk, and do not claim the residual prose is satisfied.',
  'test_sc06_epistemic_comma_scope_remains_pending',pending=True,
  proposal='Owner must choose: affirm formal clause scope and correct the residual example; or define exact adversative boundaries/epistemic termination with positive and negative examples, version the changed rule and review flips.'),
 _record('SC-07','Compound number words ending in one','4.4',210,
  'compounds `<tens>[- ]<two..nine>` (21 – 99) → digits.',
  'The explicit grammar converts twenty-two and ninety-nine, but leaves twenty-one and thirty-one literal; isolated one also remains literal.',
  ['eval/scoring_v2/normalize.py::_words','eval/scoring_v2/tables.py::NUMBER_WORDS'],
  'The prose numeric interval includes 21/31/etc., while the closed grammar excludes one and separately excludes isolated one.',
  'Unresolved: current experimental code follows the explicit two-nine grammar; no inferred one mapping is adopted.',
  'test_sc07_tens_one_grammar_remains_pending',pending=True,
  proposal='Owner must choose: clarify the stated interval to exclude every tens-plus-one value; or amend the compound grammar to one-nine while retaining isolated-one exclusion, version the behavior and review affected outputs.'),
 _record('SC-08','Unknown string result statuses','10.3 all other cases and 13.1',637,
  '`abstain_ok = status not in ("abstained", "unverified", "error")`. This is **v1\'s status-only rule, unchanged**.',
  'Unknown string statuses retain v1 status-only semantics on fact cases; non-string non-null statuses raise ValueError. Missing/null status is not silently assigned an enum value.',
  ['eval/scoring_v2/score.py::_validate','eval/scoring_v2/score.py::score_case'],
  'The API describes status but specifies no exhaustive accepted enum or rejection rule for unknown strings.',
  'Unresolved: preserve current experimental v1-compatible handling and report the missing enum policy; do not invent a new failure or acceptance policy.',
  'test_sc08_unknown_status_policy_remains_pending',pending=True,
  proposal='Owner must choose: explicitly retain v1-compatible unknown string handling; or specify a closed enum, treatment of missing/null/unknown values and versioned malformed-output/error policy before adoption.'),
]


def clarification_register():
    """Return a detached evidence register; every approval remains absent."""
    return dict(schema=REGISTER_SCHEMA,clarifications=copy.deepcopy(_RECORDS),acceptance_approved=False)


def validate_clarifications(register):
    """Validate evidence structure and prevent accidental approval laundering."""
    if not isinstance(register,dict) or set(register)!={'schema','clarifications','acceptance_approved'}:
        return ['invalid clarification register fields']
    if register['schema']!=REGISTER_SCHEMA or register['acceptance_approved'] is not False or not isinstance(register['clarifications'],list):
        return ['invalid clarification schema, approval state or records']
    errors=[];seen=set()
    for record in register['clarifications']:
        if not isinstance(record,dict) or set(record)!=set(_RECORDS[0]): errors.append('invalid clarification record fields');continue
        cid=record['id']
        if not isinstance(cid,str) or cid in seen: errors.append('duplicate or invalid clarification id')
        else: seen.add(cid)
        if record['resolution_status'] not in (RESOLVED,PENDING): errors.append(str(cid)+': invalid resolution status')
        expected=next((r for r in _RECORDS if r['id']==cid),None)
        if expected and record['resolution_status']!=expected['resolution_status']:
            errors.append(str(cid)+': authoritative resolution state cannot be silently changed')
        if record['acceptance_approved'] is not False or record['review_status']!='NOT_REVIEWED' or record['independent_review_required'] is not True:
            errors.append(str(cid)+': independent approval cannot be inferred')
        if record['resolution_status']==PENDING and not record['proposed_resolution']: errors.append(str(cid)+': missing explicit decision proposal')
        for name in ('source','implementation','evidence'):
            if not isinstance(record[name],dict) or not record[name]: errors.append(str(cid)+': missing '+name)
        for name in ('title','conflict_or_ambiguity','resolution','code_change_scope'):
            if not isinstance(record[name],str) or not record[name]: errors.append(str(cid)+': missing '+name)
    if seen!={r['id'] for r in _RECORDS}: errors.append('clarification coverage differs from reviewed source inventory')
    return errors


def clarification_summary():
    register=clarification_register()
    records=register['clarifications']
    return dict(total=len(records),resolved_engineering=sum(r['resolution_status']==RESOLVED for r in records),
                pending_ids=[r['id'] for r in records if r['resolution_status']==PENDING],
                independent_review_required=len(records),acceptance_approved=False)
