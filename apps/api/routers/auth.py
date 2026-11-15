import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from apps.api.schemas import Credentials, Me, TokenOut
from apps.api.security import current_user, hash_password, issue_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut)
def register(body: Credentials, request: Request):
    db = request.app.state.svc.db
    if db.user_by_email(body.email):
        raise HTTPException(409, "email already registered")
    uid = "u_" + uuid.uuid4().hex[:10]
    db.exec("INSERT INTO users (id,email,password_hash,settings,created) VALUES (?,?,?,?,?)",
            (uid, body.email.lower(), hash_password(body.password), "{}", time.time()))
    return TokenOut(token=issue_token(uid), user_id=uid, onboarded=False)


@router.post("/login", response_model=TokenOut)
def login(body: Credentials, request: Request):
    u = request.app.state.svc.db.user_by_email(body.email)
    if not u or not verify_password(body.password, u["password_hash"]):
        raise HTTPException(401, "wrong email or password")
    return TokenOut(token=issue_token(u["id"]), user_id=u["id"], onboarded=bool(u["onboarded"]))


@router.get("/me", response_model=Me)
def me(user=Depends(current_user)):
    return Me(user_id=user["id"], email=user["email"], persona_id=user["persona_id"],
              onboarded=bool(user["onboarded"]), settings=user["settings"])
