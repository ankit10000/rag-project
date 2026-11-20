"""Opaque server sessions and audited account operations (no provider access).

Passwords use salted scrypt. Only token/CSRF digests are persisted. Administrative
password reset is the initial release recovery mechanism; no emailed reset token
or first-registrant admin escalation exists. Call bootstrap_admin from local CLI.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import os
import re
import secrets
import uuid

from backend.errors import ApiError
from services.database import get_connection
from services.tenant_context import auth_system_context

SESSION_COOKIE = 'rag_session'
CSRF_COOKIE = 'rag_csrf'
SESSION_SECONDS = 12 * 60 * 60
# A fixed *invalid-account* hash performs the same expensive operation as a user.
_DUMMY = 'scrypt$32768$8$1$AAAAAAAAAAAAAAAAAAAAAA==$' + base64.urlsafe_b64encode(bytes(64)).decode()
_ADMIN_LOCK = 819302761


@dataclass(frozen=True)
class User:
    id: str
    email: str
    display_name: str
    role: str
    status: str
    csrf_hash: str = field(default='', repr=False)

    def public(self):
        return {key: getattr(self, key) for key in ('id', 'email', 'display_name', 'role', 'status')}


def _email(value: str) -> str:
    value = value.strip().lower()
    if len(value) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
        raise ApiError(422, 'invalid_account', 'a valid email address is required')
    return value


def _password(value: str) -> bytes:
    if not isinstance(value, str) or not 12 <= len(value) <= 1024:
        raise ApiError(422, 'invalid_password', 'password must contain 12 to 1024 characters')
    encoded = value.encode('utf-8')
    if len(encoded) > 4096:
        raise ApiError(422, 'invalid_password', 'password is too long')
    return encoded


def hash_password(password: str) -> str:
    raw = _password(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(raw, salt=salt, n=32768, r=8, p=1, dklen=64, maxmem=128 * 1024 * 1024)
    return 'scrypt$32768$8$1$' + base64.urlsafe_b64encode(salt).decode() + '$' + base64.urlsafe_b64encode(digest).decode()


def verify_password(password: str, encoded: str) -> bool:
    try:
        if not isinstance(password, str) or len(password.encode('utf-8')) > 4096:
            return False
        kind, n, r, p, salt, expected = encoded.split('$')
        # Do not let malformed persisted parameters trigger unbounded resources.
        if (kind, n, r, p) != ('scrypt', '32768', '8', '1'):
            return False
        salt_bytes = base64.b64decode(salt, altchars=b'-_', validate=True)
        expected_bytes = base64.b64decode(expected, altchars=b'-_', validate=True)
        if len(salt_bytes) != 16 or len(expected_bytes) != 64:
            return False
        actual = hashlib.scrypt(password.encode('utf-8'), salt=salt_bytes, n=32768, r=8, p=1,
                                dklen=64, maxmem=128 * 1024 * 1024)
        return hmac.compare_digest(actual, expected_bytes)
    except (ValueError, TypeError):
        return False


def secret_hash(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _audit(conn, actor, target, action):
    conn.execute('INSERT INTO audit_events(actor_user_id,target_user_id,action) VALUES(%s,%s,%s)',
                 (actor, target, action))


def _user(row, csrf='') -> User:
    return User(str(row[0]), row[1], row[2], row[3], row[4], csrf)


def register(email: str, password: str, display_name: str = '') -> None:
    """Always return the same public result, including an already registered email."""
    email = _email(email)
    if os.getenv('RAG_V2_REGISTRATION', '1') != '1':
        raise ApiError(403, 'registration_closed', 'registration is not available')
    if len(display_name) > 120:
        raise ApiError(422, 'invalid_account', 'display name is too long')
    encoded = hash_password(password)
    with auth_system_context(), get_connection() as conn:
        row = conn.execute('INSERT INTO users(id,email,password_hash,display_name,role,status) '
                           "VALUES(%s,%s,%s,%s,'user','active') ON CONFLICT(email) DO NOTHING RETURNING id",
                           (str(uuid.uuid4()), email, encoded, display_name.strip())).fetchone()
        if row:
            _audit(conn, row[0], row[0], 'account.register')


def login(email: str, password: str) -> tuple[User, str, str]:
    # Malformed and unknown account identifiers receive the same credential error.
    try:
        email = _email(email)
    except ApiError:
        email = '<invalid-account>'
    key = secret_hash(email)
    denied = ApiError(401, 'invalid_credentials', 'invalid email or password')
    authenticated = None
    with auth_system_context(), get_connection() as conn:
        # Atomic row upsert serializes attempts across processes and survives restarts.
        attempt = conn.execute('INSERT INTO auth_login_attempts(key_hash,failures,window_started_at) '
                               'VALUES(%s,1,now()) ON CONFLICT(key_hash) DO UPDATE SET '
                               "failures=CASE WHEN auth_login_attempts.window_started_at < now()-interval '15 minutes' "
                               'THEN 1 ELSE auth_login_attempts.failures+1 END, '
                               "window_started_at=CASE WHEN auth_login_attempts.window_started_at < now()-interval '15 minutes' "
                               'THEN now() ELSE auth_login_attempts.window_started_at END RETURNING failures',
                               (key,)).fetchone()
        row = conn.execute('SELECT id,email,display_name,role,status,password_hash FROM users WHERE email=%s FOR UPDATE',
                           (email,)).fetchone()
        valid = verify_password(password, row[5] if row else _DUMMY)
        if valid and row and row[4] == 'active' and attempt[0] <= 10:
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            conn.execute('INSERT INTO user_sessions(id,user_id,token_hash,csrf_hash,expires_at) VALUES(%s,%s,%s,%s,%s)',
                         (str(uuid.uuid4()), row[0], secret_hash(token), secret_hash(csrf),
                          datetime.now(timezone.utc) + timedelta(seconds=SESSION_SECONDS)))
            conn.execute('DELETE FROM auth_login_attempts WHERE key_hash=%s', (key,))
            _audit(conn, row[0], row[0], 'session.login')
            authenticated = (_user(row), token, csrf)
        else:
            # Never store submitted passwords, session material, or unknown email text.
            _audit(conn, None, row[0] if row else None, 'session.login_failed')
    # Raise only after committing the failed-attempt counter.
    if authenticated is None:
        raise denied
    return authenticated


def authenticate(token: str | None) -> User:
    if not token or not 32 <= len(token) <= 128:
        raise ApiError(401, 'unauthorized', 'authentication required')
    with auth_system_context(), get_connection() as conn:
        row = conn.execute('SELECT u.id,u.email,u.display_name,u.role,u.status,s.csrf_hash '
                           'FROM user_sessions s JOIN users u ON u.id=s.user_id '
                           "WHERE s.token_hash=%s AND s.revoked_at IS NULL AND s.expires_at>now() AND u.status='active'",
                           (secret_hash(token),)).fetchone()
    if not row:
        raise ApiError(401, 'unauthorized', 'authentication required')
    return _user(row, row[5])


def logout(token: str | None) -> None:
    if not token or len(token) > 128:
        return
    with auth_system_context(), get_connection() as conn:
        row = conn.execute('UPDATE user_sessions SET revoked_at=now() WHERE token_hash=%s AND revoked_at IS NULL '
                           'RETURNING user_id', (secret_hash(token),)).fetchone()
        if row:
            _audit(conn, row[0], row[0], 'session.logout')


def _check_admin(conn, actor: User):
    row = conn.execute('SELECT role,status FROM users WHERE id=%s FOR UPDATE', (actor.id,)).fetchone()
    if not row or tuple(row) != ('admin', 'active'):
        raise ApiError(403, 'forbidden', 'administrator access required')


def admin_update(actor: User, target_id: str, *, role: str | None = None, status: str | None = None) -> User:
    if role is not None and role not in ('admin', 'user') or status is not None and status not in ('active', 'disabled'):
        raise ApiError(422, 'invalid_account', 'invalid account status or role')
    with auth_system_context(), get_connection() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(%s)', (_ADMIN_LOCK,))
        _check_admin(conn, actor)
        row = conn.execute('SELECT id,email,display_name,role,status FROM users WHERE id=%s FOR UPDATE', (target_id,)).fetchone()
        if not row:
            raise ApiError(404, 'not_found', 'account not found')
        new_role, new_status = role or row[3], status or row[4]
        if row[3:] == ('admin', 'active') and (new_role, new_status) != ('admin', 'active'):
            count = conn.execute("SELECT count(*) FROM users WHERE role='admin' AND status='active'").fetchone()[0]
            if count <= 1:
                raise ApiError(409, 'last_admin', 'an active administrator must remain')
        updated = conn.execute('UPDATE users SET role=%s,status=%s WHERE id=%s '
                               'RETURNING id,email,display_name,role,status', (new_role, new_status, target_id)).fetchone()
        conn.execute('UPDATE user_sessions SET revoked_at=now() WHERE user_id=%s AND revoked_at IS NULL', (target_id,))
        _audit(conn, actor.id, target_id, 'admin.account_update')
        return _user(updated)


def admin_reset_password(actor: User, target_id: str, new_password: str) -> None:
    encoded = hash_password(new_password)
    with auth_system_context(), get_connection() as conn:
        _check_admin(conn, actor)
        row = conn.execute('UPDATE users SET password_hash=%s,password_changed_at=now() WHERE id=%s RETURNING id',
                           (encoded, target_id)).fetchone()
        if not row:
            raise ApiError(404, 'not_found', 'account not found')
        conn.execute('UPDATE user_sessions SET revoked_at=now() WHERE user_id=%s AND revoked_at IS NULL', (target_id,))
        _audit(conn, actor.id, target_id, 'admin.password_reset')


def bootstrap_admin(email: str, password: str, display_name: str = '') -> None:
    """Local operator-only bootstrap. Not exposed over HTTP; never promotes a user."""
    email, encoded = _email(email), hash_password(password)
    with auth_system_context(), get_connection() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(%s)', (_ADMIN_LOCK,))
        if conn.execute("SELECT 1 FROM users WHERE role='admin' LIMIT 1").fetchone():
            raise ApiError(409, 'admin_exists', 'an administrator already exists')
        if conn.execute('SELECT 1 FROM users WHERE email=%s', (email,)).fetchone():
            raise ApiError(409, 'account_exists', 'bootstrap requires a new account')
        uid = str(uuid.uuid4())
        conn.execute('INSERT INTO users(id,email,password_hash,display_name,role,status) '
                     "VALUES(%s,%s,%s,%s,'admin','active')", (uid, email, encoded, display_name.strip()))
        _audit(conn, uid, uid, 'admin.bootstrap')


def list_users(actor: User) -> list[dict]:
    with auth_system_context(), get_connection() as conn:
        _check_admin(conn, actor)
        rows = conn.execute('SELECT id,email,display_name,role,status FROM users ORDER BY created_at,id LIMIT 200').fetchall()
        return [_user(row).public() for row in rows]
