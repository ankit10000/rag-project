"""Multi-user API. V1 bearer endpoints are deliberately not mounted here."""
import os
import asyncio
import time
import logging
import uuid
import pathlib
import re
import threading
from contextlib import asynccontextmanager,nullcontext
from uuid import UUID
from fastapi import FastAPI,Depends,Request,Response,UploadFile,File,Query
from fastapi.responses import FileResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from backend import errors
from backend.errors import ApiError
from backend.v2 import auth
from backend.v2.tenant import require_user,require_admin,require_owned_conversation,verify_origin
from backend.v2.schemas import Credentials,Registration,ConversationInput,ChatInput,UserUpdate,PasswordReset,UserOut,DocumentOut,UploadOut,JobOut,ConversationOut,HistoryOut,ChatOut,MemoryListOut
from services.database import get_connection
from services.tenant_context import auth_system_context
from services.v2_coordination import resource_lock
from services.request_budget import request_budget
from services import v2_jobs as jobs

PREFIX='/api/v2'

def _allowed_hosts():
    """Exact hostnames only; private container names can be explicitly enabled."""
    hosts=[host.strip() for host in os.getenv(
        'RAG_V2_ALLOWED_HOSTS','localhost,127.0.0.1,[::1],testserver').split(',')]
    if not hosts or any(not host or (host!='[::1]' and not re.fullmatch(
            r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?',host)) for host in hosts):
        raise ValueError('RAG_V2_ALLOWED_HOSTS requires exact hostnames without ports or wildcards')
    return list(dict.fromkeys(hosts))

def _chat_generation_slots():
    value=os.getenv('RAG_V2_CHAT_CONCURRENCY','0')
    if not value.isdecimal() or not 0<=int(value)<=4:
        raise ValueError('RAG_V2_CHAT_CONCURRENCY must be between 0 and 4')
    return threading.BoundedSemaphore(int(value)) if int(value) else None

def _run_limited_turn(conversation_id,message,slots):
    from services.request_budget import budgeted_lock
    # Queued generation uses the existing total deadline. History/recovery and
    # authentication requests remain independent of this model-memory limit.
    with budgeted_lock(slots) if slots is not None else nullcontext():
        import main
        return main.run_turn(conversation_id,message)

def _storage():
    return pathlib.Path(os.getenv('RAG_V2_UPLOAD_DIR','data/v2_uploads')).resolve()

def _doc(conn,did,owner):
    r=conn.execute('SELECT id,filename,status,pages,chunks,created_at,page_metadata FROM documents WHERE id=%s AND owner_id=%s AND status<>\'deleted\'',(did,owner)).fetchone()
    if not r:raise ApiError(404,'not_found','document not found')
    return dict(zip(('id','filename','status','pages','chunks','created_at','page_metadata'),r))

def _job(conn,jid,owner):
    r=conn.execute('SELECT id,document_id,status,attempts,error_code,created_at,progress,heartbeat_at,lease_until FROM jobs WHERE id=%s AND owner_id=%s',(jid,owner)).fetchone()
    if not r:raise ApiError(404,'not_found','job not found')
    return dict(zip(('id','document_id','status','attempts','error_code','created_at','progress','heartbeat_at','lease_until'),r))

@asynccontextmanager
async def lifespan(app):
    if os.getenv('RAG_V2')!='1' or os.getenv('RAG_V2_COMPAT')=='1':raise RuntimeError('multi-user mode must be explicitly enabled')
    from services.request_budget import configured_timeout
    configured_timeout()
    from psycopg.conninfo import conninfo_to_dict
    from services.database import DATABASE_URL
    if conninfo_to_dict(DATABASE_URL or '').get('dbname')=='rag_db':raise RuntimeError('v2 must not access rag_db')
    # FORCE RLS cannot protect against a superuser or BYPASSRLS connection.
    with auth_system_context(),get_connection() as c:
        role=c.execute('SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user').fetchone()
        if not role or any(role):raise RuntimeError('v2 requires a non-superuser non-BYPASSRLS database role')
        c.execute('SELECT id FROM users LIMIT 0')
        tables=c.execute("SELECT count(*) FROM pg_class WHERE relnamespace='public'::regnamespace AND relname=ANY(%s) AND relrowsecurity AND relforcerowsecurity",(['documents','jobs','job_events','conversations','messages','conversation_memories','memory_sources','document_chunks'],)).fetchone()[0]
        if tables!=8:raise RuntimeError('v2 ownership migration is required')
    _storage().mkdir(parents=True,exist_ok=True)
    yield

def create_app():
    generation_slots=_chat_generation_slots()
    app=FastAPI(title='RAG v2',version='2.0.0',lifespan=lifespan,openapi_url=PREFIX+'/openapi.json',docs_url=PREFIX+'/docs')
    errors.install(app)
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=_allowed_hosts())

    @app.middleware('http')
    async def bounded_body(request,call_next):
        from fastapi.responses import JSONResponse
        limit=26*1024*1024 if request.url.path.startswith(PREFIX+'/documents') else 1024*1024
        from services.request_budget import configured_timeout
        deadline=time.monotonic()+configured_timeout()
        body=bytearray()
        stream=request.stream().__aiter__()
        try:
            while True:
                remaining=deadline-time.monotonic()
                if remaining<=0:raise asyncio.TimeoutError()
                part=await asyncio.wait_for(anext(stream),timeout=min(15,remaining))
                body.extend(part)
                if len(body)>limit:return JSONResponse(status_code=413,content={'error':{'code':'payload_too_large','message':'request body too large'}})
        except StopAsyncIteration:
            pass
        except asyncio.TimeoutError:
            return JSONResponse(status_code=408,content={'error':{'code':'request_timeout','message':'request body deadline exceeded'}})
        request._body=bytes(body)
        request.state.request_id=uuid.uuid4().hex
        from services.request_budget import RequestDeadlineExceeded
        try:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise RequestDeadlineExceeded()
            with request_budget(seconds=remaining,suppress_output=True):
                response=await call_next(request)
        except RequestDeadlineExceeded:
            return JSONResponse(status_code=504,content={'error':{'code':'request_timeout','message':'request deadline exceeded'}})
        except Exception as exc:
            # Do not propagate private exception text to the ASGI server's
            # traceback logger after sending a sanitized response.
            logging.getLogger('rag.api').error('unhandled request error (%s)',type(exc).__name__)
            return JSONResponse(status_code=500,content={'error':{'code':'internal_error','message':'request could not be completed'}})
        response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','X-Request-ID':request.state.request_id})
        return response

    @app.get(PREFIX+'/health')
    def health():return {'status':'ok'}

    @app.post(PREFIX+'/auth/register',status_code=201)
    def register(body:Registration,request:Request):
        verify_origin(request);auth.register(body.email,body.password,body.display_name)
        return {'message':'Account request processed. Sign in with your credentials.'}
    @app.post(PREFIX+'/auth/login',response_model=UserOut)
    def login(body:Credentials,request:Request,response:Response):
        verify_origin(request);user,token,csrf=auth.login(body.email,body.password)
        secure=os.getenv('RAG_V2_SECURE_COOKIES')=='1'
        response.set_cookie(auth.SESSION_COOKIE,token,httponly=True,secure=secure,samesite='strict',max_age=auth.SESSION_SECONDS,path='/')
        response.set_cookie(auth.CSRF_COOKIE,csrf,httponly=False,secure=secure,samesite='strict',max_age=auth.SESSION_SECONDS,path='/')
        return user.public()
    @app.get(PREFIX+'/auth/me',response_model=UserOut)
    def me(user=Depends(require_user)):return user.public()
    @app.post(PREFIX+'/auth/logout')
    def logout(request:Request,response:Response,user=Depends(require_user)):
        auth.logout(request.cookies.get(auth.SESSION_COOKIE));response.delete_cookie(auth.SESSION_COOKIE);response.delete_cookie(auth.CSRF_COOKIE)
        return {'ok':True}
    @app.get(PREFIX+'/admin/users',response_model=list[UserOut])
    def users(user=Depends(require_admin)):return auth.list_users(user)
    @app.patch(PREFIX+'/admin/users/{uid}',response_model=UserOut)
    def update_user(uid:UUID,body:UserUpdate,user=Depends(require_admin)):
        return auth.admin_update(user,str(uid),role=body.role,status=body.status).public()
    @app.post(PREFIX+'/admin/users/{uid}/reset-password')
    def reset_password(uid:UUID,body:PasswordReset,user=Depends(require_admin)):
        auth.admin_reset_password(user,str(uid),body.password);return {'ok':True}

    @app.get(PREFIX+'/documents',response_model=list[DocumentOut])
    def documents(user=Depends(require_user)):
        with get_connection() as c:
            ids=c.execute("SELECT id FROM documents WHERE owner_id=%s AND status<>'deleted' ORDER BY created_at DESC LIMIT 200",(user.id,)).fetchall()
            return [_doc(c,r[0],user.id) for r in ids]

    def save_upload(file,owner,did):
        if not file.filename or not file.filename.lower().endswith('.pdf'):raise ApiError(422,'invalid_pdf','a PDF is required')
        filename=pathlib.PurePath(file.filename.replace('\\','/')).name[:120]
        folder=_storage()/owner;folder.mkdir(parents=True,exist_ok=True)
        target=folder/(str(did)+'-'+uuid.uuid4().hex+'.pdf')
        try:
            with target.open('xb') as out:
                size=0
                while data:=file.file.read(1024*1024):
                    size+=len(data)
                    if size>25*1024*1024:raise ApiError(413,'payload_too_large','PDF is too large')
                    out.write(data)
            import pymupdf
            with pymupdf.open(target,filetype='pdf') as pdf:
                if pdf.needs_pass or not 1<=len(pdf)<=200:raise ValueError('unsuitable PDF')
        except BaseException as exc:
            target.unlink(missing_ok=True)
            if isinstance(exc,ApiError):raise
            raise ApiError(422,'invalid_pdf','PDF is unreadable, encrypted, or exceeds page limits') from None
        return filename,str(target)

    @app.post(PREFIX+'/documents',status_code=202,response_model=UploadOut)
    def upload(file:UploadFile=File(...),user=Depends(require_user)):
        did=uuid.uuid4();name,path=save_upload(file,user.id,did)
        try:
            with get_connection() as c:
                c.execute('INSERT INTO documents(id,filename,storage_path) VALUES(%s,%s,%s)',(did,name,path))
                jid=jobs.enqueue(c,did,1,str(did)+':1')
        except BaseException:
            pathlib.Path(path).unlink(missing_ok=True);raise
        return {'id':str(did),'document_id':str(did),'job_id':jid,'filename':name,'status':'queued'}
    @app.put(PREFIX+'/documents/{did}',status_code=202,response_model=UploadOut)
    def replace_document(did:UUID,file:UploadFile=File(...),user=Depends(require_user)):
        # Validate the replacement before changing the currently published file.
        with get_connection() as c:_doc(c,did,user.id)
        name,path=save_upload(file,user.id,did)
        try:
            with resource_lock(did),get_connection() as c:
                _doc(c,did,user.id)
                old=c.execute('SELECT storage_path FROM documents WHERE id=%s FOR UPDATE',(did,)).fetchone()[0]
                version=c.execute("UPDATE documents SET filename=%s,storage_path=%s,status='queued',version=version+1 WHERE id=%s RETURNING version",(name,path,did)).fetchone()[0]
                c.execute("UPDATE jobs SET status='cancelled',lease_token=NULL,lease_until=NULL WHERE document_id=%s AND status IN ('queued','running')",(did,))
                # Old chunks cannot be served as if they represent the replacement.
                c.execute('DELETE FROM document_chunks WHERE document_id=%s',(did,))
                jid=jobs.enqueue(c,did,version,str(did)+':'+str(version))
        except BaseException:
            pathlib.Path(path).unlink(missing_ok=True);raise
        pathlib.Path(old).unlink(missing_ok=True)
        return {'id':str(did),'document_id':str(did),'job_id':jid,'filename':name,'status':'queued'}
    @app.get(PREFIX+'/documents/{did}',response_model=DocumentOut)
    def document(did:UUID,user=Depends(require_user)):
        with get_connection() as c:return _doc(c,did,user.id)
    @app.get(PREFIX+'/documents/{did}/file')
    def download(did:UUID,user=Depends(require_user)):
        with get_connection() as c:
            d=_doc(c,did,user.id);r=c.execute('SELECT storage_path FROM documents WHERE id=%s AND owner_id=%s',(did,user.id)).fetchone()
        path=pathlib.Path(r[0]).resolve()
        if not path.is_relative_to(_storage()/user.id) or not path.is_file():raise ApiError(404,'not_found','document file unavailable')
        return FileResponse(path,media_type='application/pdf',filename=d['filename'],content_disposition_type='inline')
    @app.delete(PREFIX+'/documents/{did}')
    def delete_document(did:UUID,user=Depends(require_user)):
        with resource_lock(did),get_connection() as c:
            _doc(c,did,user.id)
            c.execute('SELECT id FROM documents WHERE id=%s FOR UPDATE',(did,))
            c.execute("UPDATE documents SET status='deleted',version=version+1 WHERE id=%s",(did,))
            c.execute("UPDATE jobs SET status='cancelled',lease_token=NULL,lease_until=NULL WHERE document_id=%s AND status IN ('queued','running')",(did,))
            c.execute('DELETE FROM document_chunks WHERE document_id=%s',(did,))
            path=c.execute('SELECT storage_path FROM documents WHERE id=%s',(did,)).fetchone()[0]
        pathlib.Path(path).unlink(missing_ok=True)
        return {'deleted':True}
    @app.get(PREFIX+'/jobs',response_model=list[JobOut])
    def job_list(user=Depends(require_user)):
        with get_connection() as c:return [_job(c,r[0],user.id) for r in c.execute('SELECT id FROM jobs WHERE owner_id=%s ORDER BY created_at DESC LIMIT 200',(user.id,)).fetchall()]
    @app.get(PREFIX+'/jobs/{jid}',response_model=JobOut)
    def job(jid:UUID,user=Depends(require_user)):
        with get_connection() as c:return _job(c,jid,user.id)
    @app.post(PREFIX+'/jobs/{jid}/cancel')
    def cancel(jid:UUID,user=Depends(require_user)):
        with get_connection() as c:
            _job(c,jid,user.id);return {'cancelled':jobs.cancel(c,jid)}
    @app.post(PREFIX+'/jobs/{jid}/retry')
    def retry(jid:UUID,user=Depends(require_user)):
        with get_connection() as c:
            j=_job(c,jid,user.id)
            c.execute('SELECT id FROM documents WHERE id=%s FOR UPDATE',(j['document_id'],))
            d=_doc(c,j['document_id'],user.id)
            if j['status'] not in ('failed','cancelled'):raise ApiError(409,'conflict','job is not retryable')
            version=c.execute("UPDATE documents SET version=version+1,status='queued' WHERE id=%s RETURNING version",(j['document_id'],)).fetchone()[0]
            new=jobs.enqueue(c,j['document_id'],version,str(j['document_id'])+':'+str(version))
            return {'job_id':new}
    @app.get(PREFIX+'/conversations',response_model=list[ConversationOut])
    def conversations(q:str=Query('',max_length=200),user=Depends(require_user)):
        from backend.repositories import list_conversations
        return [r for r in list_conversations(200) if q.casefold() in r['title'].casefold()]
    @app.post(PREFIX+'/conversations',status_code=201,response_model=ConversationOut)
    def create_conversation(body:ConversationInput,user=Depends(require_user)):
        from services.conversation_service import create_conversation
        return {'conversation_id':create_conversation(body.title),'title':body.title,'message_count':0}
    @app.get(PREFIX+'/conversations/{cid}',response_model=HistoryOut)
    def history(cid:UUID,user=Depends(require_user)):
        from services.v2_turn_results import history as get_history
        require_owned_conversation(user,str(cid))
        return {'conversation_id':str(cid),'messages':get_history(str(cid))}
    @app.patch(PREFIX+'/conversations/{cid}')
    def rename(cid:UUID,body:ConversationInput,user=Depends(require_user)):
        with resource_lock(cid),get_connection() as c:
            require_owned_conversation(user,str(cid));c.execute('UPDATE conversations SET title=%s WHERE id=%s AND owner_id=%s',(body.title,cid,user.id))
        return {'conversation_id':str(cid),'title':body.title}
    @app.delete(PREFIX+'/conversations/{cid}')
    def delete_conversation(cid:UUID,user=Depends(require_user)):
        from services.local_deletion_service import delete_conversation
        with resource_lock(cid):
            require_owned_conversation(user,str(cid));return {'deleted':delete_conversation(str(cid))}
    @app.get(PREFIX+'/conversations/{cid}/turns/{turn_id}')
    def recover_turn(cid:UUID,turn_id:UUID,response:Response,user=Depends(require_user)):
        from services.v2_turn_results import committed_result
        require_owned_conversation(user,str(cid))
        result=committed_result(str(cid),str(turn_id))
        if result is None:
            response.status_code=202
            return {'state':'pending','turn_id':str(turn_id)}
        return result
    @app.post(PREFIX+'/chat',response_model=ChatOut)
    def chat(body:ChatInput,user=Depends(require_user)):
        from services.v2_turn_results import committed_result,turn_identity
        if not body.message.strip():raise ApiError(422,'empty_message','message must not be blank')
        turn=str(body.turn_id or uuid.uuid4())
        with request_budget(suppress_output=True),resource_lock(body.conversation_id):
            require_owned_conversation(user,str(body.conversation_id))
            existing=committed_result(str(body.conversation_id),turn,body.message)
            if existing is not None:return existing
            with turn_identity(turn):
                result=_run_limited_turn(str(body.conversation_id),body.message,generation_slots)
            # Ordinary answers were atomically committed before memory work.
            saved=committed_result(str(body.conversation_id),turn,body.message)
            if saved is not None:return saved
            return {**result,'conversation_id':str(body.conversation_id),'answer_status':result.get('status'),'turn_id':turn}
    @app.get(PREFIX+'/memories',response_model=list[MemoryListOut])
    def all_memories(conversation_id:UUID|None=None,user=Depends(require_user)):
        from backend.routers.memories import list_memories
        with get_connection() as c:
            ids=[r[0] for r in c.execute('SELECT id FROM conversations WHERE owner_id=%s ORDER BY created_at DESC LIMIT 200',(user.id,)).fetchall()]
        if conversation_id is not None:
            require_owned_conversation(user,str(conversation_id));ids=[conversation_id]
        return [list_memories(str(cid),limit=200).model_dump() for cid in ids]
    @app.get(PREFIX+'/conversations/{cid}/memories/{mid}/sources')
    def sources(cid:UUID,mid:int,user=Depends(require_user)):
        from backend.routers.memories import memory_sources
        require_owned_conversation(user,str(cid));return memory_sources(str(cid),mid)
    @app.delete(PREFIX+'/conversations/{cid}/memories/{mid}')
    def delete_memory(cid:UUID,mid:int,user=Depends(require_user)):
        from services.local_deletion_service import delete_memory
        with resource_lock(cid):
            require_owned_conversation(user,str(cid));r=delete_memory(str(cid),mid)
            if not r.get('deleted'):raise ApiError(404,'not_found','memory not found')
            return r
    @app.delete(PREFIX+'/conversations/{cid}/messages/{mid}')
    def delete_message(cid:UUID,mid:int,user=Depends(require_user)):
        from services.local_deletion_service import delete_message
        with resource_lock(cid):
            require_owned_conversation(user,str(cid));r=delete_message(str(cid),mid)
            if not r.get('deleted'):raise ApiError(404,'not_found','message not found')
            return r
    return app
app=create_app()
