"""Local v1 HTTP contracts, startup/shutdown and deletion serialization; no DB/provider I/O."""
import testsafe
testsafe.require_scratch_db()
import contextlib
import hashlib
import threading
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.app import create_app
from backend import config

CID='11111111-1111-1111-1111-111111111111'
TOKEN='local-test-token-with-more-than-thirty-two-characters'
PREFIX='/api/v1'


class ApiContractTests(unittest.TestCase):
    def setUp(self):
        self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch('backend.app.load_token_digest',return_value=(hashlib.sha256(TOKEN.encode()).digest(),'test')))
        self.stack.enter_context(patch('backend.app._remove_stale_upload_temps'))
        self.client=self.stack.enter_context(TestClient(create_app(),base_url='http://127.0.0.1',raise_server_exceptions=False))
        self.client.headers['Authorization']='Bearer '+TOKEN

    def test_health_auth_and_lifecycle_contract(self):
        self.assertEqual(self.client.get(PREFIX+'/health').json(),{'status':'ok'})
        self.assertEqual(self.client.get(PREFIX+'/conversations',headers={'Authorization':'Bearer wrong'}).status_code,401)
        self.assertIsNotNone(self.client.app.state.token_digest)
        self.stack.close()
        self.assertIsNone(self.client.app.state.token_digest)

    def test_blank_conversation_title_matches_persisted_default(self):
        with patch('services.conversation_service.create_conversation',return_value=CID) as create:
            response=self.client.post(PREFIX+'/conversations',json={'title':'   '})
        self.assertEqual(response.status_code,201)
        self.assertEqual(response.json()['title'],'New Conversation')
        create.assert_called_once_with('New Conversation')

    def test_empty_or_malformed_chat_conversation_is_not_implicit_creation(self):
        with patch('services.conversation_service.create_conversation') as create:
            for cid in ('','not-a-uuid'):
                with self.subTest(cid=cid):
                    response=self.client.post(PREFIX+'/chat',json={'message':'hello','conversation_id':cid})
                    self.assertEqual(response.status_code,422)
            create.assert_not_called()

    def test_chat_empty_message_and_missing_conversation(self):
        response=self.client.post(PREFIX+'/chat',json={'message':'   '})
        self.assertEqual(response.status_code,422)
        with patch('services.conversation_service.conversation_exists',return_value=False):
            response=self.client.post(PREFIX+'/chat',json={'message':'hello','conversation_id':CID})
        self.assertEqual(response.status_code,404)

    def test_database_failure_response_and_logs_redact_exception_details(self):
        import psycopg
        secret='SECRET-db-password-and-private-query'
        with patch('backend.repositories._conn',side_effect=psycopg.OperationalError(secret)), \
             patch('backend.errors.log.error') as log:
            response=self.client.get(PREFIX+'/conversations')
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.json()['error']['code'],'database_unavailable')
        self.assertNotIn(secret,response.text)
        self.assertNotIn(secret,str(log.call_args_list))
        self.assertTrue(response.json()['error']['request_id'])

    def test_scoped_delete_contracts_and_not_found(self):
        with patch('services.conversation_service.conversation_exists',return_value=True), \
             patch('services.local_deletion_service.delete_conversation',return_value=True) as delete:
            response=self.client.delete(PREFIX+'/conversations/'+CID)
        self.assertEqual(response.status_code,200);self.assertTrue(response.json()['deleted'])
        delete.assert_called_once_with(CID)
        for path,function,result in [
            (f'/conversations/{CID}/messages/7','delete_message',{'deleted':True,'orphaned':[3],'still_supported':[4]}),
            (f'/conversations/{CID}/memories/3','delete_memory',{'deleted':True,'cleanup_status':'incomplete_unknown_provenance'}),
        ]:
            with patch('services.conversation_service.conversation_exists',return_value=True), \
                 patch('services.local_deletion_service.'+function,return_value=result) as delete:
                response=self.client.delete(PREFIX+path)
            self.assertEqual(response.status_code,200);self.assertTrue(response.json()['deleted'])
            if function=='delete_memory':
                self.assertEqual(response.json()['cleanup_status'],'incomplete_unknown_provenance')
            self.assertEqual(delete.call_args.args[0],CID)
            with patch('services.conversation_service.conversation_exists',return_value=True), \
                 patch('services.local_deletion_service.'+function,return_value={'deleted':False}):
                self.assertEqual(self.client.delete(PREFIX+path).status_code,404)

    def test_deletion_rejects_invalid_ids_before_service_calls(self):
        with patch('services.local_deletion_service.delete_message') as delete:
            for path in (f'/conversations/{CID}/messages/0',f'/conversations/{CID}/messages/-1',
                         f'/conversations/{CID}/messages/1.0',f'/conversations/{CID}/memories/1.0',
                         f'/conversations/{CID}/messages/true','/conversations/nope/messages/1'):
                self.assertEqual(self.client.delete(PREFIX+path).status_code,422)
            delete.assert_not_called()

    def test_delete_waits_for_active_turn_of_same_conversation(self):
        entered=threading.Event();release=threading.Event();deleted=threading.Event();responses=[]
        def turn(*args):
            entered.set()
            if not release.wait(3): raise RuntimeError('test turn was not released')
            return {'kind':'answer','answer':'ok','citations':[]}
        def delete(*args):
            deleted.set();return True
        with patch('services.conversation_service.conversation_exists',return_value=True), \
             patch('main.run_turn',side_effect=turn), \
             patch('services.local_deletion_service.delete_conversation',side_effect=delete):
            chat=threading.Thread(target=lambda:responses.append(self.client.post(PREFIX+'/chat',json={'conversation_id':CID,'message':'hello'})))
            chat.start();self.assertTrue(entered.wait(2))
            deletion=threading.Thread(target=lambda:responses.append(self.client.delete(PREFIX+'/conversations/'+CID)))
            deletion.start()
            self.assertFalse(deleted.wait(0.05))
            release.set();chat.join(3);deletion.join(3)
            self.assertFalse(chat.is_alive() or deletion.is_alive())
            self.assertTrue(deleted.is_set());self.assertEqual(sorted(r.status_code for r in responses),[200,200])

    def test_chat_waiting_behind_delete_rechecks_existence(self):
        from backend.dependencies import conversation_lock
        lock=conversation_lock(CID);lock.acquire();started=threading.Event();responses=[]
        def request():
            started.set();responses.append(self.client.post(PREFIX+'/chat',json={'conversation_id':CID,'message':'hello'}))
        with patch('services.conversation_service.conversation_exists',return_value=False),patch('main.run_turn') as turn:
            thread=threading.Thread(target=request);thread.start();self.assertTrue(started.wait(2))
            lock.release();thread.join(5)
            self.assertFalse(thread.is_alive());self.assertEqual(responses[0].status_code,404)
            turn.assert_not_called()


if __name__=='__main__':unittest.main()
