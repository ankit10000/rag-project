"""WP6: deterministic WP5 v2.1 contract tests on synthetic inputs only."""
import testsafe
testsafe.require_scratch_db()
import copy
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import unittest
from eval.probes.v2_spec_fixtures import NORMALIZATION, GUARDS, SPLITTER, case, score_rows
from eval.scoring_v2 import score_case, bind_v1_signature, validate_annotations
from eval.scoring_v2.normalize import M, contains, canon_decimal
from eval.scoring_v2.numbers import G, grounded
from eval.scoring_v2.text_units import split
from eval.scoring_v2 import context
from eval.phase35.run_eval import score_generic
from eval.framework.integrity import dataset_hash


def score(answer, c=None, ann=None, text='', status='answered', history=None, citations=None):
    c = c or case()
    result = {'answer':answer,'status':status,'citations':[{'chunk_id':1}] if citations is None else citations}
    return score_case(c,result,{1:('synthetic',1)},{1},text,c['history'] if history is None else history,ann)


class ScorerV21Tests(unittest.TestCase):
    def test_all_matching_table_rows(self):
        for pid, haystack, needle, expected in NORMALIZATION:
            with self.subTest(pid=pid):
                self.assertEqual(contains(M(haystack), M(needle)), expected)

    def test_all_numeric_guard_table_rows(self):
        for pid, answer, text, ungrounded, refs in GUARDS:
            with self.subTest(pid=pid):
                got = score(answer,case(gold=[]),text=text)
                self.assertEqual(got['ungrounded_numbers'], ungrounded)
                self.assertEqual(got['ungrounded_refs'], refs)
                self.assertEqual(got['numeric_grounded'], not ungrounded)
        self.assertEqual([(t.kind,t.value,t.unit) for t in G('Costs £16.99.')], [('currency','16.99','gbp')])
        self.assertEqual([t.kind for t in G('P-204')], ['code'])

    def test_all_sentence_splitter_table_rows(self):
        for pid,text,n_sent,n_clause,protected in SPLITTER:
            with self.subTest(pid=pid):
                sentences = split(text)
                self.assertEqual(len(sentences),n_sent)
                clauses = [c for s in sentences for c in s.clauses]
                if n_clause is not None:
                    self.assertEqual(len(clauses),n_clause)
                for span in protected:
                    self.assertTrue(any(span.casefold() in c.text.casefold() for c in clauses), span)
                if pid == 'S-08':
                    self.assertEqual(sum(c.paren for c in clauses),1)
                if pid == 'S-10':
                    self.assertTrue(sentences[0].list_intro)
                    self.assertTrue(sentences[1].bullet and sentences[2].bullet)

    def test_all_behavior_table_rows(self):
        for pid,answer,c,ann,text,status,expected in score_rows():
            with self.subTest(pid=pid):
                got = score(answer,c,ann,text,status)
                for key,value in expected.items():
                    self.assertEqual(got[key],value,key)
                if pid == 'C-02':
                    self.assertIn({'text':'2,000','family':'P'},got['signals']['excused'])
                if pid == 'H-02':
                    self.assertEqual(got['signals']['history_corrections'],['usd 85'])
                if pid == 'A-11':
                    self.assertEqual(got['signals']['abstention'],[])
                if pid == 'A-14':
                    self.assertTrue(got['signals']['error_row'])

    def test_independent_unit_currency_and_word_tables(self):
        units={'h':['h','hr','hrs','hour','hours'],'min':['min','mins','minute','minutes'],
               'day':['day','days'],'week':['week','weeks'],'month':['month','months'],'year':['year','years'],
               'working day':['working day','working days','business day','business days'],
               'l':['l','litre','litres','liter','liters'],'ml':['ml','millilitre','millilitres','milliliter','milliliters'],
               'g':['g','gram','grams'],'kg':['kg','kilogram','kilograms'],'mg':['mg','milligram','milligrams'],
               'nm':['nm','n·m','n m','newton-metre','newton-metres','newton-meter','newton-meters'],
               'mm':['mm'],'cm':['cm'],'m':['m','metre','metres','meter','meters'],'km':['km'],
               'bar':['bar'],'mm/s':['mm/s'],'mg/l':['mg/L'],'°c':['°C'],'°f':['°F']}
        for canonical,aliases in units.items():
            for alias in aliases:
                with self.subTest(alias=alias):
                    self.assertEqual(M('5.00 '+alias),'5 '+canonical)
                    self.assertFalse(contains(M('15 '+alias),M('5 '+canonical)))
        for text,expected in [('€2.50','eur 2.5'),('2.50 euros','eur 2.5'),('2 pounds sterling','gbp 2'),('$5-10','usd 5-usd 10'),('GBP 1,800-2,000','gbp 1800-gbp 2000'),('20 percent','20%'),('20 per cent','20%')]:
            with self.subTest(text=text): self.assertEqual(M(text),expected)
        for text in ['one','a','an','dozen','half','quarter','first','one hundred and twenty']:
            self.assertEqual(M(text),text)
        for text,value in [('zero','0'),('two','2'),('nineteen','19'),('twenty','20'),('ninety-nine','99')]:
            self.assertEqual(M(text),value)
        self.assertEqual(canon_decimal('3.100'),'3.1')
        self.assertEqual(M('1.0'),'1.0')
        self.assertEqual(M('13 pm'),'13 pm')
        self.assertEqual(M('noon midnight'),'noon midnight')

    def test_normalization_seeded_properties(self):
        rng=random.Random(0)
        for _ in range(160):
            n=rng.randrange(1,100000)
            raw=rng.choice([f'**{n:,} litres**',f'$ {n}.00',f'{n}% [S1]',f'\u200b{n}\u202fkg',f'“{n}”'])
            with self.subTest(raw=raw): self.assertEqual(M(M(raw)),M(raw))
            # An adjacent digit or decimal/thousands continuation is a distinct value.
            for h in [f'9{n}',f'{n}9',f'0.{n}',f'1,{n}',f'{n}.5',f'{n},5']:
                self.assertFalse(contains(h,str(n)),h)
            other=n+1
            self.assertFalse(contains(M(f'USD {other}'),M(f'USD {n}')))
        self.assertNotEqual(M('1,000'),M('1.000'))
        for protected in ['18.75','09:30','s.4.2','https://example.org/a.b?q=3.4','a.b@example.org']:
            for prefix in ['Value ','See ','Use ']:
                units=split(prefix+protected+' now. Next sentence.')
                self.assertTrue(any(protected in c.text for s in units for c in s.clauses))

    def test_closed_unicode_word_and_negation_tables(self):
        for quote in '’‘‛′': self.assertEqual(M('it'+quote+'s'),"it's")
        for quote in '“”„″': self.assertEqual(M(quote+'text'+quote),'"text"')
        for dash in '‐‑‒–—―﹘﹣－': self.assertEqual(M('16'+dash+'32'),'16-32')
        for space in '\u00a0\u2007\u2009\u202f\u200a\t': self.assertEqual(M('x'+space+'y'),'x y')
        for zero in '\u200b\ufeff': self.assertEqual(M('x'+zero+'y'),'xy')
        words='zero two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety'.split()
        values=[0,*range(2,21),30,40,50,60,70,80,90]
        for word,value in zip(words,values):
            self.assertEqual(M(word),str(value))
            self.assertNotEqual(M(word+'fold'),str(value))
        c=case(gold=[['1800']],forbidden=['2000']); ann={'forbidden':[{'text':'2000','kind':'assertion'}]}
        prefixes=['not','never','no longer','rather than','instead of','in place of',"isn't",'is not',"wasn't",'was not',"aren't",'are not',"weren't",'were not']
        for cue in prefixes:
            self.assertTrue(score('1800; '+cue+' 2000.',c,ann,'1800 2000')['correct'],cue)
            self.assertFalse(score('1800; '+cue+' absurd 2000.',c,ann,'1800 2000')['correct'],cue)
        filler='the a an its their that this these those earlier previous previously old original prior former quoted stated printed listed misprinted outdated superseded wrong incorrect erroneous value values figure figures amount amounts rate rates number of usd gbp eur'.split()
        for word in filler:
            self.assertTrue(score('1800; not '+word+' 2000.',c,ann,'1800 2000')['correct'],word)
        for cue in ['changed','changes','raised','raises','increased','increases','reduced','reduces','lowered','lowers','corrected','corrects','amended','amends','updated','updates','revised','revises','moved','moves']:
            self.assertTrue(score('1800; it '+cue+' from 2000.',c,ann,'1800 2000')['correct'],cue)
            self.assertFalse(score('1800; it '+cue+' near 2000.',c,ann,'1800 2000')['correct'],cue)
        self.assertTrue(score('1800; not the earlier old previous 2000.',c,ann,'1800 2000')['correct'])
        self.assertFalse(score('1800; not the earlier old previous quoted 2000.',c,ann,'1800 2000')['correct'])

    def test_typed_unit_propagation_and_grounding_direction(self):
        for text in ['30 or 18 months','30 and 18 months','30-18 months','30 to 18 months','between 30 and 18 months','30, 24 and 18 months']:
            with self.subTest(text=text):
                self.assertTrue(all(t.kind=='measure' and t.unit=='month' for t in G(text)))
        self.assertFalse(grounded(G('$85')[0],G('85 g 85')))
        self.assertTrue(grounded(G('85')[0],G('$85')))
        self.assertFalse(grounded(G('-5')[0],G('5')))
        self.assertEqual(G('Twenty days'),[])

    def test_numeric_grounding_fact_residual_and_unavailable_context(self):
        got=score('30 days and $999.',text='30 days')
        self.assertTrue(got['correct']) # V-6 default: only unsupported for fact cases.
        self.assertTrue(got['unsupported'])
        self.assertEqual(got['ungrounded_numbers'],['usd 999'])
        got=score('30 days and $999.',text=None)
        self.assertIsNone(got['numeric_grounded'])
        self.assertIsNone(got['ungrounded_numbers'])
        self.assertTrue(got['signals']['context_unavailable'])

    def test_per_occurrence_literals_and_hedges_cannot_be_excused(self):
        c=case(gold=[['1800']],forbidden=['2000'])
        ann={'forbidden':[{'text':'2000','kind':'assertion'}]}
        for answer in ['1800 not 2000; 2000 is the cap.','1800 not 2000 or 1800.','1800 not between 2000 and 1800.']:
            self.assertFalse(score(answer,c,ann,'1800 2000')['correct'])
        self.assertFalse(score('30 days; not APPROVED',case(forbidden=['APPROVED']),text='30 days')['correct'])
        self.assertTrue(score('30 days; UNAPPROVED',case(forbidden=['APPROVED']),text='30 days')['correct'])
        c=case(gold=[['$65']],history=[{'role':'assistant','content':'The fee is $85.'}])
        got=score('$85 was wrong. $85. The fee is $65.',c,text='$65')
        self.assertFalse(got['correct'])
        self.assertEqual(got['history_echo'],['usd 85'])
        self.assertEqual(got['signals']['history_corrections'],['usd 85'])
        got=score('$85 was wrong, but $85 is fine. The fee is $65.',c,text='$65')
        self.assertFalse(got['correct'])
        self.assertEqual(got['history_echo'],['usd 85'])
        self.assertEqual(got['signals']['history_corrections'],['usd 85'])

    def test_negatable_groups_and_conflict_status_are_not_sufficient(self):
        c=case(gold=[['same appointment']])
        self.assertEqual(score('They cannot be given at the same appointment.',c,{'negatable_groups':[0]})['fact_recall'],0.0)
        c=case(gold=[['3000'],['2500']],conflict=True)
        self.assertFalse(score('3000. 2500.',c,status='conflict')['conflict_ok'])
        self.assertTrue(score('3000. 2500.',c,status='conflict')['signals']['status_conflict'])
        self.assertFalse(score('They differ: 3000 and 2500.',c,{'conflict_groups':[[0,1]]},citations=[])['conflict_ok'])

    def test_api_keys_determinism_adapter_and_input_immutability(self):
        c=case(); result={'answer':'30 days','status':'answered','citations':[{'chunk_id':1}]}
        args=(c,result,{1:('synthetic',1)},{1},'30 days',[],{})
        before=copy.deepcopy(args); a=score_case(*args)
        self.assertEqual(a,score_case(*args)); self.assertEqual(args,before)
        self.assertTrue(set(score_generic(*args[:5])) <= set(a))
        self.assertEqual(a['scorer_name'],'phase35-scorer'); self.assertEqual(a['scorer_version'],'2.1.0')
        self.assertEqual(a['tables_version'],'2.1.0')
        self.assertEqual(bind_v1_signature({'cases':{'SYN':{}}})(*args[:5]),a)
        with self.assertRaises(KeyError): bind_v1_signature({'cases':{}})(*args[:5])
        self.assertEqual(score_case(*args[:-1],None),a)

    def test_per_entry_annotation_validation_failures(self):
        c=case(gold=[['30 days']],forbidden=['20 days'],history=[{'role':'assistant','content':'20 days'}])
        bad=[{'forbidden':[{'text':'20 days','kind':'unknown'}]},
             {'forbidden':[{'text':'20 days','kind':'literal','allowed_with':['pump']}]},
             {'forbidden':[{'text':'20 days','kind':'distractor','allowed_with':[]}]},
             {'forbidden':[{'text':'30 days','kind':'assertion'}]},
             {'history_wrong_values':[{'text':'20 days','turn':5}]},
             {'history_wrong_values':[{'text':'21 days','turn':0}]},
             {'negatable_groups':[1]}, {'negatable_groups':[True]}, {'conflict_groups':[[0,0]]},
             {'disclosure':[{'pattern':'('}]}, {'disclosure':[{'pattern_set':'unknown'}]},
             {'forbidden':[{'text':'20 days','kind':'literal'},{'text':'20 days','kind':'assertion'}]}]
        for ann in bad:
            with self.subTest(ann=ann), self.assertRaises(ValueError): score('30 days',c,ann,'30 days')

    def test_full_annotation_validation_av1_through_av10(self):
        c=case(gold=[['30 days']],forbidden=['20 days'],history=[{'role':'assistant','content':'20 days'}])
        docs={'synthetic':['Pump P-204 requires 20 days; P-205 requires 30 days.']}
        ann={'schema':'phase35-scorer-annotations/1','dataset_version':'synthetic',
             'dataset_sha256':dataset_hash([c]),'cases':{'SYN':{'forbidden':[{'text':'20 days','kind':'assertion','source':'dataset'}]}}}
        self.assertEqual(validate_annotations(ann,[c],docs),[])
        bad=[]
        for update in [{'schema':'wrong'},{'extra':True},{'dataset_sha256':'0'*64},{'cases':{}}]:
            modified=copy.deepcopy(ann); modified.update(update); bad.append(modified)
        for entry in [{}, {'forbidden':[{'text':'20 days','kind':'literal','source':'annotation'}]},
                      {'forbidden':[{'text':'20 days','kind':'distractor','allowed_with':['nonexistent']}]},
                      {'history_wrong_values':[{'text':'30 days','turn':0}]}, {'negatable_groups':[99]},
                      {'disclosure':[{'pattern_set':'generic_leak_v1'}]},
                      {'forbidden':[{'text':'20 days','kind':'literal'},{'text':'20 days','kind':'literal'}]}]:
            modified=copy.deepcopy(ann); modified['cases']['SYN']=entry; bad.append(modified)
        for modified in bad:
            with self.subTest(modified=modified): self.assertTrue(validate_annotations(modified,[c],docs))

    def test_context_verification_fails_closed_for_altered_refs(self):
        c=case(); docs={'synthetic':['Thirty days apply to this synthetic policy text with enough words.',
                                   'Non-gold page two has unrelated context for deterministic selection.',
                                   'Non-gold page three has different unrelated context for selection.']}
        items,pair,ids,text,valid=context.tier1_items(c,docs)
        row={'context':[{'chunk_id':i['chunk'][0],'document':i['chunk'][1],'page':i['chunk'][2],'gold':pair[i['chunk'][0]] is not None} for i in items]}
        self.assertEqual(context.verify_tier1(row,c,docs)[3],'exact')
        row['context'][0]['page']=99
        got=context.verify_tier1(row,c,docs); self.assertIsNone(got[2]); self.assertEqual(got[3],'mismatch:order_or_ref')
        table=[{'id':1,'document':'synthetic','page':1,'sha256':context.text_sha256('text'),'content':'text'}]
        row={'retrieved':[{'chunk_id':1,'document_name':'synthetic','page_number':1}],'citations':[{'chunk_id':1,'document':'synthetic','page':1}]}
        self.assertEqual(context.verify_tier2(row,table,c)[3],'exact')
        row['citations'][0]['page']=2
        self.assertEqual(context.verify_tier2(row,table,c)[3],'mismatch:ref')
        self.assertIsNone(context.verify_tier2(row,table,c)[2])
        row['citations']=[]
        self.assertEqual(context.verify_tier2(row,table,c,{'chunk_count':2})[3],'mismatch:chunk_count')
        self.assertEqual(context.verify_tier2(row,table,c,{'chunk_table_sha256':'bad'})[3],'mismatch:chunk_table_sha256')

    def test_probe_harness_subsignal_negative_control(self):
        from eval.probes import scorer_regression as harness
        from eval.probes.probe_data import PROBES
        probe=copy.deepcopy(PROBES[0])
        initial=harness.run(probes=[probe],v2_fn=score_case)[0]
        probe['v2_signals']={'fact_recall':initial['v2_score']['fact_recall'],
                             'numeric_grounded':initial['v2_score']['numeric_grounded']}
        positive=harness.run(probes=[probe],v2_fn=score_case)[0]
        self.assertEqual(positive['v2_mismatches'],[])
        probe['v2_signals']['fact_recall']=initial['v2_score']['fact_recall']+0.5
        negative=harness.run(probes=[probe],v2_fn=score_case)[0]
        self.assertEqual(len(negative['v2_mismatches']),1)
        self.assertIn('fact_recall:',negative['v2_mismatches'][0])
        self.assertEqual(initial['v2_score'],negative['v2_score'])

    def test_malformed_input_shapes_fail_explicitly(self):
        baseline=[case(),{'answer':'30 days','status':'answered','citations':[]},{1:('synthetic',1)},{1},'30 days',[],{}]
        malformed=[(0,None),(1,None),(1,[]),(2,[]),(3,[]),(4,123),(5,None),
                   (5,[{'role':'system','content':'x'}]),(5,[{'role':'user','content':123}]),
                   (1,{'answer':123}),(1,{'answer':{}}),(1,{'status':123}),(1,{'status':{}}),
                   *[(1,{'citations':value}) for value in ['bad',{},False,0,'']],
                   (1,{'citations':[{}]}),(1,{'citations':[{'chunk_id':True}]}),
                   (2,{True:None}),(2,{1:'bad'}),(2,{1:('synthetic',True)}),(3,{True}),
                   (0,dict(case(),gold_sources={})),(0,dict(case(),gold_sources=[{'document':'x','page':True}])),
                   (0,dict(case(),question=None)),(0,dict(case(),gold_facts='bad')),
                   (0,dict(case(),gold_facts=[[]])),(0,dict(case(),gold_facts=[[123]])),
                   (0,dict(case(),forbidden='bad')),(0,dict(case(),forbidden=[None]))]
        for index,value in malformed:
            args=copy.deepcopy(baseline); args[index]=value
            with self.subTest(index=index,value=value),self.assertRaises(ValueError): score_case(*args)
        # Null/missing answers are valid empty outputs, and absent context is
        # explicitly represented as None rather than a made-up numeric result.
        for result in [{},{'answer':None}]:
            args=copy.deepcopy(baseline); args[1]=result
            self.assertEqual(score_case(*args)['fact_recall'],0.0)

    def test_import_isolation_and_frozen_v1_bytes(self):
        script="import builtins,sys; builtins.open=lambda *a,**k: (_ for _ in ()).throw(AssertionError('file read')); import eval.scoring_v2; assert not any(x=='services' or x.startswith('services.') for x in sys.modules); assert not hasattr(eval.scoring_v2,'score_generic')"
        result=subprocess.run([sys.executable,'-B','-c',script],text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(hashlib.sha256(Path('eval/answer_scoring.py').read_bytes()).hexdigest(),'c3b5422820b96266be8529e853653ebc40184e3b48e2cd7991f68663cf8167af')
        self.assertNotIn('scoring_v2',Path('eval/phase35/run_eval.py').read_text())


if __name__=='__main__': unittest.main()
