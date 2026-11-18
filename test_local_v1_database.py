"""Local v1 connection bounds preserve psycopg transaction/close semantics."""
import testsafe
testsafe.require_scratch_db()
import os
import unittest
from unittest.mock import MagicMock,patch
from services import database


class DatabasePolicyTests(unittest.TestCase):
    def test_scratch_runner_uri_supports_legacy_harness_and_escapes_credentials(self):
        from scripts import local_v1_scratch as scratch
        from psycopg.conninfo import conninfo_to_dict
        settings=dict(dbname='rag_test_scratch',user='fixture-user',password='fake:p@ss/word',host='127.0.0.1',port='5432')
        with patch.object(scratch,'scratch_info',return_value=settings):
            url=scratch.scratch_url()
        self.assertEqual(url.rsplit('/',1)[1],'rag_test_scratch')
        self.assertEqual(conninfo_to_dict(url)['password'],settings['password'])
        self.assertEqual(conninfo_to_dict(url)['dbname'],'rag_test_scratch')

    def test_connection_and_statement_timeouts_are_explicit(self):
        conn=MagicMock()
        with patch.dict(os.environ,{},clear=True),patch.object(database,'DATABASE_URL','postgresql://localhost/rag_test_scratch'),patch.object(database.psycopg,'connect',return_value=conn) as connect,patch.object(database,'register_vector') as vector:
            self.assertIs(database.get_connection(),conn)
        self.assertEqual(connect.call_args.kwargs['connect_timeout'],5)
        self.assertIn('statement_timeout=15000',connect.call_args.kwargs['options'])
        self.assertIn('lock_timeout=5000',connect.call_args.kwargs['options'])
        vector.assert_called_once_with(conn)
        conn.__enter__.assert_not_called()
        conn.close.assert_not_called()

    def test_timeout_overrides_are_bounded_and_preserve_other_options(self):
        settings=dict(DB_CONNECT_TIMEOUT_SECONDS='7',DB_STATEMENT_TIMEOUT_MS='2000',DB_LOCK_TIMEOUT_MS='500')
        with patch.dict(os.environ,settings,clear=True),patch.object(database,'DATABASE_URL',"dbname=rag_test_scratch options='-c application_name=local-test'"),patch.object(database.psycopg,'connect') as connect,patch.object(database,'register_vector'):
            database.get_connection()
        self.assertEqual(connect.call_args.kwargs['connect_timeout'],7)
        self.assertIn('application_name=local-test',connect.call_args.kwargs['options'])
        self.assertIn('statement_timeout=2000',connect.call_args.kwargs['options'])

    def test_invalid_timeout_refuses_connection_without_exposing_url(self):
        for key,value in [('DB_CONNECT_TIMEOUT_SECONDS','0'),('DB_CONNECT_TIMEOUT_SECONDS','61'),('DB_STATEMENT_TIMEOUT_MS','300001'),('DB_LOCK_TIMEOUT_MS','-1'),('DB_STATEMENT_TIMEOUT_MS','bad')]:
            with self.subTest(key=key,value=value),patch.dict(os.environ,{key:value},clear=True),patch.object(database,'DATABASE_URL','postgresql://secret:password@localhost/rag_test_scratch'),patch.object(database.psycopg,'connect') as connect:
                with self.assertRaises(ValueError) as error:database.get_connection()
                self.assertNotIn('password',str(error.exception))
                connect.assert_not_called()

    def test_failed_vector_registration_closes_connection(self):
        conn=MagicMock()
        with patch.object(database,'DATABASE_URL','postgresql://localhost/rag_test_scratch'),patch.object(database.psycopg,'connect',return_value=conn),patch.object(database,'register_vector',side_effect=RuntimeError('registration failed')):
            with self.assertRaises(RuntimeError):database.get_connection()
        conn.close.assert_called_once()

    def test_active_request_budget_clamps_timeouts_or_refuses_short_connect(self):
        from services.request_budget import RequestDeadlineExceeded
        with patch.object(database,'DATABASE_URL','postgresql://localhost/rag_test_scratch'),patch.object(database.psycopg,'connect') as connect,patch.object(database,'register_vector'),patch('services.request_budget.remaining_seconds',return_value=3.25):
            database.get_connection()
            self.assertEqual(connect.call_args.kwargs['connect_timeout'],3)
            self.assertIn('statement_timeout=3250',connect.call_args.kwargs['options'])
        with patch.object(database,'DATABASE_URL','postgresql://localhost/rag_test_scratch'),patch.object(database.psycopg,'connect') as connect,patch('services.request_budget.remaining_seconds',return_value=1.5):
            with self.assertRaises(RequestDeadlineExceeded):database.get_connection()
            connect.assert_not_called()

    def test_connections_are_not_shared_between_requests(self):
        first,second=MagicMock(),MagicMock()
        with patch.object(database,'DATABASE_URL','postgresql://localhost/rag_test_scratch'),patch.object(database.psycopg,'connect',side_effect=[first,second]),patch.object(database,'register_vector'):
            self.assertIs(database.get_connection(),first)
            self.assertIs(database.get_connection(),second)


@unittest.skipUnless(os.environ.get('LOCAL_V1_DB_INTEGRATION')=='1','explicit scratch integration not selected')
class DatabaseIntegrationTests(unittest.TestCase):
    def test_server_enforces_statement_timeout_and_context_closes(self):
        import psycopg
        with patch.dict(os.environ,{'DB_STATEMENT_TIMEOUT_MS':'40'}):
            conn=database.get_connection()
            with self.assertRaises(psycopg.errors.QueryCanceled):
                with conn:
                    self.assertEqual(conn.execute('SELECT current_database()').fetchone()[0],'rag_test_scratch')
                    conn.execute('SELECT pg_sleep(0.2)')
            self.assertTrue(conn.closed)
        conn=database.get_connection()
        with conn:
            self.assertEqual(conn.execute('SELECT current_database()').fetchone()[0],'rag_test_scratch')
            self.assertEqual(conn.execute('SHOW statement_timeout').fetchone()[0],'15s')
            self.assertEqual(conn.execute('SELECT 1').fetchone()[0],1)
        self.assertTrue(conn.closed)


if __name__=='__main__':unittest.main()
