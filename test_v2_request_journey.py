"""Cross-turn request regressions using synthetic current source rows. No external I/O."""
import os
import unittest
from unittest.mock import Mock, patch

from services import rag_service
from services.answer_service import generate_grounded_answer
from services.context_assembly_service import assemble_context
from services.tenant_context import tenant_scope
from services.v2_evidence_recovery import recover_complementary_evidence


OWNER = "00000000-0000-4000-8000-000000000033"
DOC = "fb115eee-bc96-4709-a6dc-c51fd5c18aaf"


def context(*texts):
    return assemble_context([
        {"chunk": (i, DOC, i, text, 0.6), "rrf_score": 0.04, "rerank_score": 0.9}
        for i, text in enumerate(texts, 1)
    ])


class RequestJourneyTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {"RAG_V2": "1"}))
        self.enterContext(tenant_scope(OWNER))
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("unexpected I/O")))

    def employment_turn(self, question, history, source_rows):
        with patch("services.database.get_connection") as conn, \
             patch.object(rag_service, "rewrite_query", return_value=question), \
             patch.object(rag_service, "classify_question", return_value="DOCUMENT"), \
             patch.object(rag_service, "hybrid_search_detailed", return_value={"results": [], "rerank_status": "ok"}):
            conn.return_value.__enter__.return_value.execute.return_value.fetchall.return_value = source_rows
            return rag_service.ask_question(question, history)

    def test_followup_and_challenge_recheck_source_in_current_turn(self):
        first = "When did Noel join Indigo Labs?"
        original = [(72, DOC, 1, "Employee: Noel Vance.\nIndigo Labs | July 2023 to October 2024")]
        joining = self.employment_turn(first, [], original)
        self.assertIn("July 2023", joining["answer"])
        history = [{"role": "user", "content": first}, {"role": "assistant", "content": joining["answer"]}]
        months = self.employment_turn("How many months?", history, original)
        self.assertEqual(months.get("status"), "answered")
        self.assertEqual(months["calculation"]["total_months"], 15)
        history += [{"role": "user", "content": "How many months?"},
                    {"role": "assistant", "content": "Noel worked there for 90 months [S1]."}]
        current = [(83, DOC, 2, "Employee: Noel Vance.\nIndigo Labs | July 2023 to November 2024")]
        rechecked = self.employment_turn("Are you sure?", history, current)
        self.assertEqual(rechecked.get("status"), "answered")
        self.assertEqual(rechecked["calculation"]["total_months"], 16)
        self.assertEqual(rechecked["citations"][0]["chunk_id"], 83)
        self.assertEqual(rechecked["citations"][0]["page"], 2)
        self.assertNotIn("90 months", rechecked["answer"])

    def test_switch_employer_then_use_new_subject(self):
        history = [{"role":"user","content":"When did Pam join Violet Agency?"},
                   {"role":"assistant","content":"Pam joined in January 2000 [S1]."},
                   {"role":"user","content":"When did Pam join Amaranth Labs?"}]
        rows = [(4, DOC, 1, "Employee: Pam Alcott.\nViolet Agency | April 2017 to April 2019"),
                (5, DOC, 1, "Employee: Pam Alcott.\nAmaranth Labs | September 2022 to November 2023")]
        result = self.employment_turn("How many months?", history, rows)
        self.assertEqual(result.get("status"), "answered")
        self.assertEqual(result["calculation"]["total_months"], 14)
        self.assertEqual(result["citations"][0]["chunk_id"], 5)

    def test_obsolete_value_with_explicit_authoritative_erratum(self):
        question = "What is the current Harbor travel allowance?"
        sources = context("Original Harbor travel allowance: 14 credits.",
                          "Official erratum to the Harbor travel allowance: the 19-credit allowance supersedes the original 14-credit allowance.")
        stale = "[DOCUMENT] The Harbor travel allowance is 14 credits [S1]."
        fixed = "[DOCUMENT] The corrected Harbor travel allowance is 19 credits [S2]."
        with patch("services.answer_service.cfg.ANSWER_MAX_RETRIES", 1):
            model = Mock(side_effect=[stale, fixed])
            result = generate_grounded_answer(question, sources, "DOCUMENT", model)
        self.assertEqual(result["status"], "answered")
        self.assertIn("19 credits", result["answer"])
        self.assertIn(2, [item["page"] for item in result["citations"]])
        self.assertLessEqual(model.call_count, 2)

    def test_provider_failure_is_not_source_absence(self):
        provider = Mock(side_effect=ConnectionError("synthetic offline provider"))
        try:
            result = generate_grounded_answer("What is the port code?", context("Port code: 296."),
                                              "DOCUMENT", provider)
        except (ConnectionError, RuntimeError):
            return
        self.assertIn(result["status"], {"error", "failed", "unverified"})
        self.assertNotIn("couldn't find", result["answer"].lower())

    def test_enumeration_recovers_second_page_and_cites_each_original_page(self):
        question = "List all three approval phases."
        anchor = {"chunk": (93, DOC, 4, "Phase 1: Planning. Phase 2: Pilot.", 0.5),
                  "rrf_score": 0.04, "rerank_score": 2.0}
        next_page = (94, DOC, 5, "Phase 3: Launch.")
        no_more = Mock(return_value={"results": [], "rerank_status": "ok"})
        with patch("services.v2_evidence_recovery._adjacent_chunks", return_value=[next_page]) as neighbours:
            recovered = recover_complementary_evidence(
                question, question, [anchor], {"results": [anchor], "rerank_status": "ok"},
                no_more, document_names=[DOC], max_chunks=2, max_chars=1000)
        self.assertTrue(neighbours.called)
        self.assertTrue(all(c.args[1:] == ([DOC], OWNER) for c in neighbours.call_args_list))
        source = assemble_context(recovered["results"])
        self.assertEqual([(s["chunk_id"], s["page_number"]) for s in source["sources"]], [(93, 4), (94, 5)])
        first = "[DOCUMENT] Phase 1 is Planning [S1]. Phase 2 is Pilot [S1]."
        complete = first + " Phase 3 is Launch [S2]."
        model = Mock(side_effect=[first, complete])
        with patch("services.answer_service.cfg.ANSWER_MAX_RETRIES", 1):
            answer = generate_grounded_answer(question, source, "DOCUMENT", model)
        self.assertEqual(model.call_count, 2)
        self.assertEqual(answer["status"], "answered")
        self.assertIn("Launch [S2]", answer["answer"])
        self.assertEqual({(c["document"],c["chunk_id"],c["page"]) for c in answer["citations"]},
                         {(DOC,93,4), (DOC,94,5)})

    def test_exhausted_one_sided_comparison_is_partial_with_source(self):
        question = "Compare Amber Hosting and Indigo Hosting in terms of cost."
        sources = context("Amber Hosting: the operating cost is 12 credits.",
                          "Indigo Hosting: the operating cost is 17 credits.")
        one_side = "[DOCUMENT] Amber Hosting costs 12 credits [S1]."
        model = Mock(return_value=one_side)
        with patch("services.answer_service.cfg.ANSWER_MAX_RETRIES", 1):
            answer = generate_grounded_answer(question, sources, "DOCUMENT", model)
        self.assertEqual(model.call_count, 2)
        self.assertEqual(answer["status"], "partial")
        self.assertIn("12 credits [S1]",answer["answer"])
        self.assertIn("Indigo Hosting",answer["answer"])
        self.assertNotIn("17",answer["answer"])
        self.assertEqual({(c["document"], c["page"]) for c in answer["citations"]}, {(DOC,1)})

    def test_failed_search_is_not_source_absence(self):
        question = "What is the carrier's charter reference?"
        failed = {"results": [], "rerank_status": "failed:RuntimeError"}
        with patch.object(rag_service, "hybrid_search_detailed", return_value=failed), \
             patch.object(rag_service, "generate_answer") as provider:
            try:
                result = rag_service._answer_from_route(question, question, "DOCUMENT", [], "")
            except RuntimeError:
                provider.assert_not_called()
                return
        provider.assert_not_called()
        self.assertIn(result["status"], {"error", "failed", "unverified"})
        self.assertNotIn("couldn't find", result["answer"].lower())


if __name__ == "__main__":
    unittest.main()
