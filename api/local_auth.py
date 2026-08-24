# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""
Local auth backend for citra-decks (standalone OSS product).

citra-decks vendors `citra_auth` as JWT-*verification* middleware only —
it has never included an issuer (that job belonged to Citra-AI's separate
user-service, which this repo doesn't carry). EmailAuthScreen.js, ported
from Citra-UI for the shell's login screen, needs something to
authenticate against, so this adds the smallest issuer that satisfies
JWTAuthMiddleware's contract: bcrypt-hashed passwords in a `users`
collection, JWTs signed with the same JWT_SECRET the middleware verifies
against, and a `personal_sa_id` minted once at registration —
folder_management.py's create_folder rejects any request without one
(the folder-per-artifact model can't create a folder otherwise).
"""

import os
import re
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from CRUD_utils import get_mongo_client, MONGODB_DATABASE

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
JWT_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days


def get_users_collection():
    client = get_mongo_client()
    return client[MONGODB_DATABASE].users


def _issue_token(user_doc: dict) -> str:
    secret = os.getenv("JWT_SECRET")
    if not secret:
        # Same failure the middleware itself raises at startup if unset —
        # fail loud rather than mint an unverifiable token.
        raise HTTPException(status_code=500, detail="JWT_SECRET not configured")
    issuer = os.getenv("JWT_ISSUER", "Citra-AI")
    now = int(datetime.now(timezone.utc).timestamp())
    payload = {
        "user_id": user_doc["_id"],
        "email": user_doc["_id"],
        "name": user_doc.get("name") or user_doc["_id"],
        "roles": ["user"],
        # Consumed by folder_management.py / presentation_api.py / etc. —
        # every personal-output resource (folders, presentations, printables,
        # reports) is stamped with this as its owner.
        "personal_sa_id": user_doc["personal_sa_id"],
        "jti": str(uuid.uuid4()),
        "iss": issuer,
        "iat": now,
        "exp": now + JWT_TTL_SECONDS,
    }
    token = jwt.encode(payload, secret, algorithm="HS256")
    return token.decode("utf-8") if isinstance(token, bytes) else token


def _public_user(user_doc: dict) -> dict:
    return {
        "email": user_doc["_id"],
        "name": user_doc.get("name") or user_doc["_id"],
    }


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(..., min_length=8)
    name: Optional[str] = None
    termsAcceptedAt: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


@router.post("/local/register")
async def register(body: RegisterRequest):
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Enter a valid email address.")

    users = get_users_collection()
    if users.find_one({"_id": email}):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    password_hash = bcrypt.hashpw(body.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    now = datetime.now(timezone.utc)
    user_doc = {
        "_id": email,
        "email": email,
        "name": body.name or email,
        "password_hash": password_hash,
        "personal_sa_id": f"sa_personal_{uuid.uuid4()}",
        "terms_accepted_at": body.termsAcceptedAt,
        "created_at": now,
        "updated_at": now,
    }
    users.insert_one(user_doc)
    logger.info(f"🔐 [LOCAL_AUTH] Registered new user: {email}")

    token = _issue_token(user_doc)
    return {"success": True, "data": {"token": token, "user": _public_user(user_doc)}}


@router.post("/local/login")
async def login(body: LoginRequest):
    email = body.email.strip().lower()
    users = get_users_collection()
    user_doc = users.find_one({"_id": email})
    if not user_doc or not bcrypt.checkpw(
        body.password.encode("utf-8"), user_doc["password_hash"].encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    token = _issue_token(user_doc)
    return {"success": True, "data": {"token": token, "user": _public_user(user_doc)}}


@router.post("/local/forgot-password")
async def forgot_password(body: ForgotPasswordRequest):
    # No email delivery wired up — same generic response whether or not the
    # account exists, so this can't be used to enumerate registered emails.
    return {"message": "If an account exists, a reset link has been sent."}


@router.get("/me")
async def me(request: Request):
    """Hit by authService.js's validateToken() — 401 (via JWTAuthMiddleware,
    this path isn't public) means invalid/expired, 200 means the token's good."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"email": user.get("email"), "name": user.get("name")}
