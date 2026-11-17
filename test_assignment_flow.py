"""Deterministic actual-turn orchestration regression tests; no DB/provider I/O."""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql:///rag_test_scratch')
import testsafe
testsafe.require_scratch_db()
import contextlib
import io
import unittest
from unittest.mock import patch
import main as app
from services import memory_service as memory
from services import automatic_memory_service as automatic
from services import legacy_provenance_quarantine as quarantine


class FlowTests(unittest.TestCase):
    def turn(self, extraction=None, error=None):
        batch = [{'id': i, 'role': 'user' if i % 2 else 'assistant', 'content': str(i)} for i in range(1, 5)]
        with contextlib.ExitStack() as stack:
            for name, value in {
                'is_explicit_memory_delete_request': False,
                'get_conversation_history': [{'id': 1, 'role': 'user', 'content': 'secret'}, {'id': 5, 'role': 'user', 'content': 'safe'}],
                'get_blocked_source_message_ids': {1, 2},
                'build_supported_memory_summary': 'supported summary',
                'assemble_memory_context': {'text': 'eligible context'},
                'ask_question': {'answer': 'ok', 'sources': [], 'status': 'answered'},
                'save_message': 9,
                'get_messages_for_memory_extraction': batch,
                'update_long_term_memory': None,
            }.items():
                stack.enter_context(patch.object(app, name, return_value=value))
            checkpoint = stack.enter_context(patch.object(app, 'update_memory_extraction_checkpoint'))
            extract = stack.enter_context(patch.object(app, 'extract_and_save_memories', return_value=extraction, side_effect=error))
            ask = app.ask_question
            summary = app.build_supported_memory_summary
            context = app.assemble_memory_context
            with contextlib.redirect_stdout(io.StringIO()):
                result = app.run_turn('c', 'question', exclude_memory_ids=[7])
            return result, checkpoint, extract, ask, summary, context

    def test_exclusions_reach_actual_answer_history_and_summary(self):
        result, checkpoint, extract, ask, summary, context = self.turn([])
        self.assertEqual(ask.call_args.kwargs['history'], [{'role': 'user', 'content': 'safe'}])
        self.assertEqual(ask.call_args.kwargs['memory_summary'], 'supported summary\neligible context')
        summary.assert_called_once_with('c', [7])
        self.assertEqual(context.call_args.kwargs['exclude_memory_ids'], [7])
        self.assertEqual([m['id'] for m in extract.call_args.kwargs['messages']], [3, 4])
        checkpoint.assert_called_once_with(conversation_id='c', last_message_id=4)
        self.assertEqual(result['memory_extraction'], 'checkpoint_advanced')

    def test_malformed_and_provider_failure_do_not_checkpoint(self):
        for failure, outcome in [(memory.MemoryExtractionError('malformed'), 'rejected_will_retry'), (RuntimeError('provider failure'), 'failed_will_retry')]:
            with self.subTest(outcome=outcome):
                result, checkpoint, *_ = self.turn(error=failure)
                checkpoint.assert_not_called()
                self.assertEqual(result['memory_extraction'], outcome)

    def test_failed_turn_can_retry_successfully(self):
        first, checkpoint, *_ = self.turn(error=memory.MemoryExtractionError('partial'))
        checkpoint.assert_not_called()
        second, checkpoint, *_ = self.turn([])
        self.assertEqual(second['memory_extraction'], 'checkpoint_advanced')
        self.assertEqual(first['answer'], second['answer'])

    def test_unknown_processing_status_rejects_extraction(self):
        item = {'memory': 'User likes tea', 'source_message_ids': [1]}
        with patch.object(memory, 'extract_memories', return_value=[item]), patch.object(memory, 'validate_source_messages'), patch.object(memory, 'process_memory', return_value='BROKEN'):
            with self.assertRaises(memory.MemoryExtractionError):
                memory.extract_and_save_memories('c', [{'id': 1, 'role': 'user'}])

    def test_cleanup_failure_fences_history_and_extraction(self):
        with patch.object(app, 'is_explicit_memory_delete_request', return_value=True), \
             patch.object(app, 'delete_matching_memories', return_value={'status': 'DELETE', 'deleted_count': 1, 'deleted_memories': [{'id': 7, 'memory': 'secret'}]}), \
             patch.object(app, 'save_message', side_effect=[10, 11]), \
             patch.object(app, 'apply_deletion_cleanup', side_effect=RuntimeError('injected cleanup failure')), \
             patch.object(app, 'clear_summary_and_advance_checkpoints') as fence, \
             contextlib.redirect_stdout(io.StringIO()):
            result = app.run_turn('c', 'forget secret')
        fence.assert_called_once_with('c')
        self.assertEqual(result['cleanup'], 'failed')
        self.assertEqual(result['deleted_count'], 1)

    def test_deletion_turn_save_failure_still_fences_history(self):
        for responses in [[RuntimeError('first save failed')], [10, RuntimeError('second save failed')]]:
            with self.subTest(responses=len(responses)), \
                 patch.object(app, 'is_explicit_memory_delete_request', return_value=True), \
                 patch.object(app, 'delete_matching_memories', return_value={'status': 'DELETE', 'deleted_count': 1}), \
                 patch.object(app, 'save_message', side_effect=responses), \
                 patch.object(app, 'clear_summary_and_advance_checkpoints') as fence, \
                 patch.object(app, 'apply_deletion_cleanup') as cleanup:
                with self.assertRaisesRegex(RuntimeError, 'save failed'):
                    app.run_turn('c', 'forget secret')
                fence.assert_called_once_with('c')
                cleanup.assert_not_called()

    def test_supported_summary_is_bounded_and_preserves_whole_newest_facts(self):
        rows = [(mid, f'fact {mid:03d} complete.') for mid in range(1, 61)]
        rows.append((61, 'OVERSIZED ' + 'x' * (memory.SUMMARY_MAX_CHARACTERS + 1)))
        with patch.object(automatic, 'get_all_conversation_memories', return_value=rows), \
             patch.object(quarantine, 'filter_supported_memories', side_effect=lambda cid, rows, **kw: rows), \
             patch.object(memory, 'generate_answer', side_effect=AssertionError('no provider')):
            summary = memory.build_supported_memory_summary('c')
        self.assertLessEqual(len(summary), memory.SUMMARY_MAX_CHARACTERS)
        self.assertNotIn('OVERSIZED', summary)
        self.assertIn('- fact 060 complete.', summary)
        self.assertIn('- fact 011 complete.', summary)
        self.assertNotIn('fact 010', summary)
        self.assertEqual(sum(line.startswith('- ') for line in summary.splitlines()), memory.SUMMARY_MAX_MEMORIES)
        # Exercise character budget separately from the count limit.
        long_rows = [(mid, str(mid) + 'z' * 1200 + ' END') for mid in range(1, 8)]
        with patch.object(automatic, 'get_all_conversation_memories', return_value=long_rows), \
             patch.object(quarantine, 'filter_supported_memories', side_effect=lambda cid, rows, **kw: rows):
            summary = memory.build_supported_memory_summary('c')
        self.assertLessEqual(len(summary), memory.SUMMARY_MAX_CHARACTERS)
        for line in summary.splitlines():
            if line.startswith('- '):
                self.assertTrue(line.endswith(' END'))


if __name__ == '__main__':
    unittest.main()
