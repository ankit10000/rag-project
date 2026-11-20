"""Scratch-only durable turn/history contracts; never real providers."""
import os,unittest,uuid,secrets
from unittest.mock import patch

@unittest.skipUnless(os.getenv('RAG_V2_DB_TEST')=='1','explicit scratch integration required')
class BrowserContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from scripts.v2_scratch import connect,app_url
        with connect(app_url()):pass
        cls.env=patch.dict(os.environ,{'DATABASE_URL':app_url(),'RAG_V2':'1','RAG_V2_COMPAT':'0','LOCAL_V1_PROFILE':'0'})
        cls.env.start()
        import psycopg
        original=psycopg.connect
        def guarded(*a,**kw):
            c=original(*a,**kw)
            if c.execute('SELECT current_database()').fetchone()[0]!='rag_test_scratch':
                c.close();raise AssertionError('wrong database')
            c.commit();return c
        cls.guard=patch.object(psycopg,'connect',side_effect=guarded);cls.guard.start()
        from services import database
        cls.url=patch.object(database,'DATABASE_URL',app_url());cls.url.start()
        cls.owner='97de44e7-f332-494b-95e1-86a432350198'
        cls.other='25973a8a-09db-4a15-a686-304a5c986eec'
        cls.sessions=[];cls.headers=[]
        from backend.v2.auth import secret_hash
        from services.tenant_context import auth_system_context
        with auth_system_context(),database.get_connection() as c:
            for owner in (cls.owner,cls.other):
                token,csrf=secrets.token_urlsafe(32),secrets.token_urlsafe(32);sid=str(uuid.uuid4());cls.sessions.append(sid)
                c.execute("INSERT INTO user_sessions(id,user_id,token_hash,csrf_hash,expires_at) VALUES(%s,%s,%s,%s,now()+interval '1 hour')",(sid,owner,secret_hash(token),secret_hash(csrf)))
                cls.headers.append({'cookie':f'rag_session={token}; rag_csrf={csrf}','x-csrf-token':csrf})
        from fastapi.testclient import TestClient
        from backend.v2.app import create_app
        cls.client=TestClient(create_app());cls.client.__enter__()
        cls.cids=[]
    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None,None,None)
        from services.tenant_context import tenant_scope,auth_system_context
        from services.database import get_connection
        with tenant_scope(cls.owner),get_connection() as c:
            c.execute('DELETE FROM conversations WHERE id=ANY(%s::uuid[])',(cls.cids,))
        with auth_system_context(),get_connection() as c:
            c.execute('DELETE FROM user_sessions WHERE id=ANY(%s::uuid[])',(cls.sessions,))
        cls.url.stop();cls.guard.stop();cls.env.stop()
    def fixture(self):
        from services.tenant_context import tenant_scope
        from services.conversation_service import create_conversation
        with tenant_scope(self.owner):cid=create_conversation('Browser closure contract fixture')
        self.cids.append(cid)
        return cid,str(uuid.uuid4())
    def result(self,page=2):
        return {'answer':'Bachelor of Engineering [S1].','status':'answered','citations':[{'ref':'S1','document':'567ee27b-074a-4d09-9af5-5dd796b8667e','page':page,'chunk_id':128}]}
    def save(self,cid,turn,result=None):
        from services.tenant_context import tenant_scope
        from services.v2_turn_results import turn_identity,save_committed_turn
        with tenant_scope(self.owner),turn_identity(turn):save_committed_turn(cid,'Question',result or self.result())
    def test_atomic_pair_rolls_back_if_assistant_insert_cannot_be_built(self):
        from services.tenant_context import tenant_scope
        from services.database import get_connection
        cid,turn=self.fixture()
        with self.assertRaises(KeyError):self.save(cid,turn,{'status':'answered'})
        with tenant_scope(self.owner),get_connection() as c:self.assertEqual(c.execute('SELECT count(*) FROM messages WHERE conversation_id=%s',(cid,)).fetchone()[0],0)
    def test_history_preserves_verified_metadata_and_ids(self):
        cid,turn=self.fixture();self.save(cid,turn)
        r=self.client.get(f'/api/v2/conversations/{cid}',headers=self.headers[0]);self.assertEqual(r.status_code,200,r.text)
        messages=r.json()['messages'];self.assertEqual(len(messages),2)
        a=messages[1];self.assertEqual(a['turn_id'],turn);m=a['answer_metadata']
        self.assertEqual(m['answer_status'],'answered');self.assertEqual(m['citations'][0]['page'],2)
        self.assertEqual(m['citations'][0]['document'],'Browser_Check_Morgan_Vale.pdf')
    def test_retry_idempotency_and_changed_input_conflict(self):
        cid,turn=self.fixture()
        def fake(cid,q):self.save(cid,turn);return self.result()
        payload={'conversation_id':cid,'turn_id':turn,'message':'Question'}
        with patch('main.run_turn',side_effect=fake) as generate:
            a=self.client.post('/api/v2/chat',json=payload,headers=self.headers[0]);b=self.client.post('/api/v2/chat',json=payload,headers=self.headers[0]);self.assertEqual(a.status_code,200,a.text);self.assertEqual(b.json(),a.json());self.assertEqual(generate.call_count,1)
            payload['message']='Different';self.assertEqual(self.client.post('/api/v2/chat',json=payload,headers=self.headers[0]).status_code,409)
    def test_other_owner_cannot_recover_or_open_history(self):
        cid,turn=self.fixture();self.save(cid,turn)
        for path in (f'/conversations/{cid}',f'/conversations/{cid}/turns/{turn}'):
            self.assertEqual(self.client.get('/api/v2'+path,headers=self.headers[1]).status_code,404)
    def test_excluded_turn_cannot_be_resurrected(self):
        from services.tenant_context import tenant_scope
        from services.database import get_connection
        cid,turn=self.fixture();self.save(cid,turn)
        with tenant_scope(self.owner),get_connection() as c:c.execute('UPDATE messages SET context_excluded=true WHERE conversation_id=%s',(cid,))
        self.assertEqual(self.client.get(f'/api/v2/conversations/{cid}/turns/{turn}',headers=self.headers[0]).status_code,410)
    def test_physically_removed_pair_cannot_regenerate_on_retry(self):
        from services.tenant_context import tenant_scope
        from services.database import get_connection
        cid,turn=self.fixture();self.save(cid,turn)
        with tenant_scope(self.owner),get_connection() as c:c.execute('DELETE FROM messages WHERE conversation_id=%s',(cid,))
        with patch('main.run_turn') as generate:
            r=self.client.post('/api/v2/chat',json={'conversation_id':cid,'turn_id':turn,'message':'Question'},headers=self.headers[0])
            self.assertEqual(r.status_code,410,r.text);generate.assert_not_called()

    def test_wrong_original_page_is_never_hydrated(self):
        cid,turn=self.fixture();self.save(cid,turn,self.result(page=1))
        r=self.client.get(f'/api/v2/conversations/{cid}/turns/{turn}',headers=self.headers[0]);self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['citations'],[])

if __name__=='__main__':unittest.main(verbosity=2)
