import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode, urlsplit

import jwt
from fastapi import Request, Response
from fastapi.responses import RedirectResponse

from obs.audit import audit
from obs.auth import fail, token
from obs.db import connection
from obs.integrations.http import request as upstream
from obs.settings import require_live, settings


def metadata() -> dict:
    require_live()
    issuer = settings().oidc_issuer.rstrip("/")
    data = upstream("GET", issuer + "/.well-known/openid-configuration")
    if data.get("issuer", "").rstrip("/") != issuer:
        fail(503, "oidc_configuration", "Identity provider issuer mismatch.")
    for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        if urlsplit(data.get(key, "")).scheme != "https":
            fail(503, "oidc_configuration", "Identity provider requires HTTPS endpoints.")
    return data


def start() -> Response:
    config = settings()
    if config.auth_provider != "oidc":
        fail(404, "sso_disabled", "SSO is not configured.")
    data = metadata()
    state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    with connection() as conn:
        conn.execute(
            "INSERT INTO obs.oidc_states(state_hash,nonce,verifier,expires_at) VALUES(%s,%s,%s,%s)",
            (
                hashlib.sha256(state.encode()).hexdigest(),
                nonce,
                verifier,
                datetime.now(UTC) + timedelta(minutes=5),
            ),
        )
    response = RedirectResponse(
        data["authorization_endpoint"]
        + "?"
        + urlencode(
            {
                "client_id": config.oidc_client_id,
                "response_type": "code",
                "scope": "openid email profile",
                "redirect_uri": config.console_url.rstrip("/") + "/api/auth/oidc/callback",
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        ),
        status_code=302,
    )
    response.set_cookie(
        "obs_oidc_state",
        state,
        max_age=300,
        secure=True,
        httponly=True,
        samesite="lax",
        path="/api/auth/oidc",
    )
    return response


def identity(claims: dict) -> dict:
    config = settings()
    if claims.get("email_verified") is not True or not claims.get("email"):
        fail(403, "unverified_identity", "A verified email address is required.")
    groups = claims.get(config.oidc_groups_claim, [])
    if not isinstance(groups, list) or any(not isinstance(g, str) for g in groups):
        fail(403, "invalid_groups", "Identity provider did not return the configured group claim.")
    roles = [config.oidc_group_roles[g] for g in groups if g in config.oidc_group_roles]
    if not roles:
        fail(403, "access_denied", "Your account is not assigned to a console access group.")
    role = max(roles, key={"viewer": 0, "operator": 1, "admin": 2}.__getitem__)
    email = claims["email"].lower()
    with connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(110541)")
        existing = conn.execute(
            "SELECT u.* FROM obs.oidc_identities i JOIN obs.users u USING(user_id) WHERE i.issuer=%s AND i.subject=%s",
            (claims["iss"], claims["sub"]),
        ).fetchone()
        if existing and existing.get("status") == "disabled":
            fail(401, "authentication_failed", "Unable to authenticate with this account.")
        if not existing:
            if conn.execute("SELECT 1 FROM obs.users WHERE email=%s", (email,)).fetchone():
                fail(
                    403,
                    "identity_conflict",
                    "This email belongs to a different identity. Contact an administrator.",
                )
            existing = conn.execute(
                "INSERT INTO obs.users(email,display_name,role) VALUES(%s,%s,%s) RETURNING *",
                (email, claims.get("name", email), role),
            ).fetchone()
            conn.execute(
                "INSERT INTO obs.oidc_identities(issuer,subject,user_id) VALUES(%s,%s,%s)",
                (claims["iss"], claims["sub"], existing["user_id"]),
            )
        conn.execute(
            "UPDATE obs.users SET role=%s,display_name=%s WHERE user_id=%s",
            (role, claims.get("name", email), existing["user_id"]),
        )
        # Invalidate earlier sessions so removed privileges cannot survive this login.
        conn.execute(
            "UPDATE obs.sessions SET revoked_at=now() WHERE user_id=%s", (existing["user_id"],)
        )
        audit(conn, email, "oidc_login", str(existing["user_id"]), {"role": role})
    return {**existing, "role": role}


def callback(request: Request, code: str = "", state: str = "") -> Response:
    cookie = request.cookies.get("obs_oidc_state", "")
    if not cookie or not state or not secrets.compare_digest(cookie, state):
        fail(400, "oidc_state", "Sign-in expired or state did not match. Start sign-in again.")
    with connection() as conn:
        saved = conn.execute(
            "DELETE FROM obs.oidc_states WHERE state_hash=%s AND expires_at>now() RETURNING *",
            (hashlib.sha256(state.encode()).hexdigest(),),
        ).fetchone()
    if not saved or not code:
        fail(400, "oidc_state", "Sign-in expired. Start sign-in again.")
    config, data = settings(), metadata()
    tokens = upstream(
        "POST",
        data["token_endpoint"],
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": config.console_url.rstrip("/") + "/api/auth/oidc/callback",
            "client_id": config.oidc_client_id,
            "client_secret": config.oidc_client_secret,
            "code_verifier": saved["verifier"],
        },
    )
    try:
        encoded = tokens["id_token"]
        jwks = upstream("GET", data["jwks_uri"])
        header = jwt.get_unverified_header(encoded)
        candidates = [
            k
            for k in jwks["keys"]
            if k.get("kid") == header.get("kid") and k.get("use", "sig") == "sig"
        ]
        if len(candidates) != 1 or header.get("alg") not in {"RS256", "ES256"}:
            raise ValueError("Signing key mismatch")
        key = jwt.PyJWK.from_dict(candidates[0], algorithm=header["alg"]).key
        claims = jwt.decode(
            encoded,
            key,
            algorithms=[header["alg"]],
            audience=config.oidc_client_id,
            issuer=data["issuer"],
            options={"require": ["exp", "iat", "iss", "sub", "aud", "nonce"]},
            leeway=30,
        )
        if not secrets.compare_digest(claims["nonce"], saved["nonce"]):
            raise ValueError("Nonce mismatch")
        if (
            isinstance(claims["aud"], list) and len(claims["aud"]) > 1 or "azp" in claims
        ) and claims.get("azp") != config.oidc_client_id:
            raise ValueError("Authorized party mismatch")
    except (jwt.PyJWTError, ValueError, KeyError, TypeError) as exc:
        fail(401, "oidc_token", "Identity provider returned an invalid identity token.")
        raise RuntimeError from exc
    user = identity(claims)
    response = RedirectResponse("/", status_code=302)
    response.delete_cookie(
        "obs_oidc_state", path="/api/auth/oidc", secure=True, httponly=True, samesite="lax"
    )
    response.set_cookie(
        "obs_session",
        token(user, secrets.token_urlsafe(32)),
        max_age=config.session_absolute_days * 86400,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/api",
    )
    return response
