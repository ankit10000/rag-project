"""Scratch safety, deletion lifecycle, rollback and actual restore rehearsal."""
import testsafe
testsafe.require_scratch_db()
import os
import unittest
import uuid
from unittest.mock import patch
from scripts import local_v1_scratch as scratch
from services import local_deletion_service as deletion
from services.database import get_connection


class ScratchGuardTests(unittest.TestCase):
    def test_production_and_system_names_refused_before_any_connection(self):
        for name in ('rag_db','postgres','template0','rag_test_scratch_other','',None):
            with self.subTest(name=name),patch.object(scratch.psycopg,'connect') as connect:
                with self.assertRaises(ValueError):scratch.connect(name)
                connect.assert_not_called()

    def test_initialization_allows_only_existing_application_migrations(self):
        self.assertEqual(scratch.MIGRATIONS,('000_base_schema.sql','001_add_messages_context_excluded.sql','002_add_memory_sources.sql','003_memory_sources_provenance.sql'))


@unittest.skipUnless(os.environ.get('LOCAL_V1_DB_INTEGRATION')=='1','explicit scratch integration not selected')
class DeletionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.cid,self.other=uuid.uuid4(),uuid.uuid4()
        with get_connection() as conn:
            self.assertEqual(conn.execute('SELECT current_database()').fetchone()[0],'rag_test_scratch')
            for cid in (self.cid,self.other):conn.execute('INSERT INTO conversations(id,title,summary) VALUES(%s,%s,%s)',(cid,'local-v1 deletion fixture','unsafe old summary'))
            self.user=conn.execute("INSERT INTO messages(conversation_id,role,content) VALUES(%s,'user','I prefer tea.') RETURNING id",(self.cid,)).fetchone()[0]
            self.assistant=conn.execute("INSERT INTO messages(conversation_id,role,content) VALUES(%s,'assistant','Tea noted.') RETURNING id",(self.cid,)).fetchone()[0]
            self.foreign=conn.execute("INSERT INTO messages(conversation_id,role,content) VALUES(%s,'user','Unrelated.') RETURNING id",(self.other,)).fetchone()[0]
            vector='['+','.join(['1']+['0']*383)+']'
            self.memory=conn.execute('INSERT INTO conversation_memories(conversation_id,memory,embedding,source_message_id) VALUES(%s,%s,%s::vector,%s) RETURNING id',(self.cid,'User prefers tea.',vector,self.user)).fetchone()[0]
            conn.execute("INSERT INTO memory_sources(conversation_id,memory_id,source_message_id,link_kind,source_role) VALUES(%s,%s,%s,'origin','user')",(self.cid,self.memory,self.user))

    def tearDown(self):
        with get_connection() as conn:
            self.assertEqual(conn.execute('SELECT current_database()').fetchone()[0],'rag_test_scratch')
            conn.execute('DELETE FROM conversations WHERE id=ANY(%s::uuid[])',([self.cid,self.other],))

    def test_message_delete_fences_and_excludes_immediate_assistant(self):
        result=deletion.delete_message(str(self.cid),self.user)
        self.assertEqual(result,dict(deleted=True,orphaned=[self.memory],still_supported=[]))
        with get_connection() as conn:
            self.assertEqual(conn.execute('SELECT context_excluded FROM messages WHERE id=%s',(self.assistant,)).fetchone(),(True,))
            summary,checkpoint=conn.execute('SELECT summary,memory_extraction_up_to_message_id FROM conversations WHERE id=%s',(self.cid,)).fetchone()
            self.assertEqual(summary,'');self.assertGreaterEqual(checkpoint,self.assistant)
            self.assertIsNotNone(conn.execute('SELECT id FROM messages WHERE conversation_id=%s AND id=%s',(self.other,self.foreign)).fetchone())

    def test_foreign_message_and_memory_deletion_are_noops(self):
        self.assertFalse(deletion.delete_message(str(self.cid),self.foreign)['deleted'])
        self.assertFalse(deletion.delete_memory(str(self.other),self.memory)['deleted'])

    def test_message_fence_failure_rolls_back_every_mutation(self):
        with patch.object(deletion,'_fence',side_effect=RuntimeError('injected fence failure')):
            with self.assertRaises(RuntimeError):deletion.delete_message(str(self.cid),self.user)
        with get_connection() as conn:
            self.assertIsNotNone(conn.execute('SELECT id FROM messages WHERE id=%s',(self.user,)).fetchone())
            self.assertEqual(conn.execute('SELECT source_message_id FROM conversation_memories WHERE id=%s',(self.memory,)).fetchone(),(self.user,))
            self.assertEqual(conn.execute('SELECT context_excluded FROM messages WHERE id=%s',(self.assistant,)).fetchone(),(False,))

    def test_memory_delete_excludes_all_sources_and_pairs_atomically(self):
        result=deletion.delete_memory(str(self.cid),self.memory)
        self.assertTrue(result['deleted'])
        self.assertEqual(result['sources_excluded'],[self.user,self.assistant])
        self.assertEqual(result['cleanup_status'],'source_fenced')
        with get_connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM memory_sources WHERE memory_id=%s',(self.memory,)).fetchone(),(0,))

    def test_unknown_provenance_deletion_never_claims_complete_cleanup(self):
        with get_connection() as conn:
            self.assertEqual(conn.execute('SELECT current_database()').fetchone()[0],'rag_test_scratch')
            conn.execute('DELETE FROM memory_sources WHERE memory_id=%s',(self.memory,))
            conn.execute('UPDATE conversation_memories SET source_message_id=NULL WHERE id=%s',(self.memory,))
        result=deletion.delete_memory(str(self.cid),self.memory)
        self.assertTrue(result['deleted'])
        self.assertEqual(result['cleanup_status'],'incomplete_unknown_provenance')
        self.assertEqual(result['sources_excluded'],[])
        with get_connection() as conn:
            self.assertEqual(conn.execute('SELECT summary FROM conversations WHERE id=%s',(self.cid,)).fetchone(),('',))
            self.assertEqual(conn.execute('SELECT context_excluded FROM messages WHERE id=%s',(self.user,)).fetchone(),(False,))

    def test_conversation_delete_cascades_only_its_own_data(self):
        self.assertTrue(deletion.delete_conversation(str(self.cid)))
        self.assertFalse(deletion.delete_conversation(str(self.cid)))
        with get_connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM messages WHERE conversation_id=%s',(self.cid,)).fetchone(),(0,))
            self.assertIsNotNone(conn.execute('SELECT id FROM conversations WHERE id=%s',(self.other,)).fetchone())


@unittest.skipUnless(os.environ.get('LOCAL_V1_RESTORE_DRILL')=='1','explicit isolated restore drill not selected')
class RestoreDrillTests(unittest.TestCase):
    def test_actual_custom_dump_restore_preserves_memory_provenance(self):
        result=scratch.restore_drill()
        self.assertEqual(result['provenance_rows_verified'],1)
        self.assertEqual(result['document_chunks_verified'],1)
        self.assertGreater(result['backup_bytes'],0)
        self.assertFalse(result['original_application_database_accessed'])
        print('Restore drill verified:',result['source_database'],'->',result['restore_database'])


if __name__=='__main__':unittest.main()
