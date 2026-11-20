"""Deterministic auth guards; real database journeys are run by the integration suite."""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import os
import unittest
from unittest.mock import patch
import uuid

from backend.errors import ApiError
from backend.v2 import auth, tenant
from services import tenant_context
from starlette.requests import Request

UID = str(uuid.uuid4())


def request(method='GET', headers=()):
    return Request({'type':'http','method':method,'headers':list(headers), 'path':'/api/v2/test',
                    'server':('localhost',3000),'scheme':'http','query_string':b''})


class PasswordTests(unittest.TestCase):
    def test_scrypt_salt_and_verification(self):
        a = auth.hash_password('correct horse battery staple')
        b = auth.hash_password('correct horse battery staple')
        self.assertNotEqual(a, b)
        self.assertTrue(auth.verify_password('correct horse battery staple', a))
        self.assertFalse(auth.verify_password('wrong password', a))
        self.assertNotIn('correct horse', a)

    def test_malformed_or_unbounded_hash_rejected(self):
        for value in ('bad', 'scrypt$999999999$8$1$AA==$AA==', auth._DUMMY.replace('$8$', '$9$')):
            self.assertFalse(auth.verify_password('some password', value))
        self.assertFalse(auth.verify_password('x'*5000, auth._DUMMY))

    def test_password_policy(self):
        for value in ('short', 'x'*1025):
            with self.assertRaises(ApiError):
                auth.hash_password(value)

    def test_public_user_never_exposes_secret_digest(self):
        user = auth.User(UID, 'a@example.test', 'A', 'user', 'active', 'csrf-secret-digest')
        self.assertNotIn('csrf', str(user.public()))
        self.assertNotIn('csrf-secret', repr(user))

    def test_invalid_tokens_fail_without_database(self):
        with patch.object(auth, 'get_connection', side_effect=AssertionError('must not connect')):
            for token in (None, '', 'short', 'x'*129):
                with self.assertRaises(ApiError) as ctx:
                    auth.authenticate(token)
                self.assertEqual(ctx.exception.status_code,401)


class TenantContextTests(unittest.TestCase):
    def test_context_nested_and_reset(self):
        self.assertIsNone(tenant_context.current_owner())
        with tenant_context.tenant_scope(UID):
            self.assertEqual(tenant_context.current_owner(), UID)
            with tenant_context.tenant_scope(str(uuid.UUID(int=2))):
                self.assertEqual(tenant_context.current_owner(),str(uuid.UUID(int=2)))
            self.assertEqual(tenant_context.current_owner(),UID)
        self.assertIsNone(tenant_context.current_owner())

    def test_fail_closed_without_owner(self):
        with patch.dict(os.environ, {'RAG_V2':'1','RAG_V2_COMPAT':'0'}):
            with self.assertRaises(PermissionError):tenant_context.database_scope()
            with tenant_context.auth_system_context():
                self.assertEqual(tenant_context.database_scope(),('v2',''))
            with tenant_context.tenant_scope(UID):
                self.assertEqual(tenant_context.database_scope(),('v2',UID))

    def test_explicit_legacy_compatibility_only(self):
        with patch.dict(os.environ,{'RAG_V2':'0','RAG_V2_COMPAT':'0'}):
            self.assertIsNone(tenant_context.database_scope())
        with patch.dict(os.environ,{'RAG_V2':'0','RAG_V2_COMPAT':'1'}):
            self.assertEqual(tenant_context.database_scope(),('legacy',''))
        with patch.dict(os.environ,{'RAG_V2':'1','RAG_V2_COMPAT':'1'}):
            with self.assertRaises(RuntimeError):tenant_context.database_scope()

    def test_auth_context_does_not_bypass_rls(self):
        with patch.dict(os.environ,{'RAG_V2':'1','RAG_V2_COMPAT':'0'}):
            with tenant_context.auth_system_context():
                self.assertEqual(tenant_context.database_scope(),('v2',''))
            with tenant_context.tenant_scope(UID), tenant_context.auth_system_context():
                self.assertEqual(tenant_context.database_scope(),('v2',UID))


class DependencyTests(unittest.TestCase):
    def setUp(self):
        self.csrf='z'*43
        self.user=auth.User(UID,'a@example.test','A','user','active',auth.secret_hash(self.csrf))

    def check(self,req):
        async def run():
            dep=tenant.require_user(req)
            try:
                value=await anext(dep)
                self.assertEqual(value,self.user)
                self.assertEqual(tenant_context.current_owner(),UID)
            finally:
                await dep.aclose()
            self.assertIsNone(tenant_context.current_owner())
        with patch.object(tenant,'authenticate',return_value=self.user):asyncio.run(run())

    def test_get_binds_and_resets_owner(self):self.check(request())

    def test_write_requires_session_bound_csrf(self):
        for csrf in ('', 'wrong'*9):
            with self.assertRaises(ApiError) as ctx:
                self.check(request('POST',[(b'x-csrf-token',csrf.encode())]))
            self.assertEqual(ctx.exception.status_code,403)
        self.check(request('POST',[(b'x-csrf-token',self.csrf.encode())]))

    def test_foreign_origin_denied(self):
        with self.assertRaises(ApiError):
            self.check(request('DELETE',[(b'origin',b'https://evil.example'),(b'x-csrf-token',self.csrf.encode())]))
        self.check(request('DELETE',[(b'origin',b'http://localhost:3000'),(b'x-csrf-token',self.csrf.encode())]))

    def test_authentication_error_preserved(self):
        async def run():
            dep=tenant.require_user(request())
            try:await anext(dep)
            finally:await dep.aclose()
        with patch.object(tenant,'authenticate',side_effect=ApiError(401,'unauthorized','authentication required')):
            with self.assertRaises(ApiError) as ctx:asyncio.run(run())
        self.assertEqual(ctx.exception.status_code,401)
        self.assertIsNone(tenant_context.current_owner())

    def test_non_admin_cannot_use_admin_dependency(self):
        with self.assertRaises(ApiError) as ctx:asyncio.run(tenant.require_admin(self.user))
        self.assertEqual(ctx.exception.status_code,403)


class DatabaseBindingTests(unittest.TestCase):
    def test_connection_sets_transaction_local_rls_values(self):
        from services import database
        from unittest.mock import MagicMock
        conn=MagicMock()
        with patch.dict(os.environ,{'RAG_V2':'1','RAG_V2_COMPAT':'0'}), tenant_context.tenant_scope(UID):
            with patch.object(database,'DATABASE_URL','postgresql://test@localhost/rag_test_scratch'), patch.object(database.psycopg,'connect',return_value=conn), patch.object(database,'register_vector'):
                self.assertIs(database.get_connection()._conn,conn)
        statement,values=conn.execute.call_args.args
        self.assertEqual(values,('v2',UID))
        self.assertIn("set_config('app.user_id', %s, true)",statement)

    def test_missing_tenant_fails_before_connect(self):
        from services import database
        with patch.dict(os.environ,{'RAG_V2':'1','RAG_V2_COMPAT':'0'}), patch.object(database.psycopg,'connect') as connect:
            with self.assertRaises(PermissionError):database.get_connection()
            connect.assert_not_called()

    def test_auth_system_connection_cannot_select_an_owner(self):
        from services import database
        from unittest.mock import MagicMock
        conn=MagicMock()
        with patch.dict(os.environ,{'RAG_V2':'1','RAG_V2_COMPAT':'0'}), tenant_context.auth_system_context():
            with patch.object(database,'DATABASE_URL','postgresql://test@localhost/rag_test_scratch'), patch.object(database.psycopg,'connect',return_value=conn), patch.object(database,'register_vector'):
                database.get_connection()
        self.assertEqual(conn.execute.call_args.args[1],('v2',''))


class AuthTransactionTests(unittest.TestCase):
    def test_failed_login_is_committed_before_error_and_no_secrets_audited(self):
        from unittest.mock import MagicMock
        conn=MagicMock(); cursor=MagicMock()
        cursor.fetchone.side_effect=[(1,),None]
        conn.execute.return_value=cursor
        @contextmanager
        def connection():
            yield conn
            committed.append(True)
        committed=[]
        with patch.object(auth,'get_connection',side_effect=connection), patch.object(auth,'verify_password',return_value=False):
            with self.assertRaises(ApiError) as ctx:auth.login('missing@example.test','a secret password')
        self.assertEqual(ctx.exception.status_code,401)
        self.assertEqual(committed,[True])
        self.assertNotIn('a secret password',str(conn.execute.call_args_list))
        self.assertIn('session.login_failed',str(conn.execute.call_args_list))

    def test_success_stores_only_session_and_csrf_hashes(self):
        from unittest.mock import MagicMock
        conn=MagicMock();cursor=MagicMock()
        cursor.fetchone.side_effect=[(1,),(UID,'a@example.test','A','user','active','password-hash')]
        conn.execute.return_value=cursor
        @contextmanager
        def connection():yield conn
        with patch.object(auth,'get_connection',side_effect=connection),patch.object(auth,'verify_password',return_value=True):
            user,token,csrf=auth.login('a@example.test','a secret password')
        calls=str(conn.execute.call_args_list)
        self.assertNotIn(token,calls)
        self.assertNotIn(csrf,calls)
        self.assertIn(auth.secret_hash(token),calls)
        self.assertIn(auth.secret_hash(csrf),calls)
        self.assertEqual(user.id,UID)


if __name__=='__main__':unittest.main()
