"""
Users module — RBAC (Admin vs Technician) with bcrypt password hashing.

Storage: MongoDB local (`users` collection). Keeps Supabase free of auth concerns
and is consistent with how other auth/metadata is already stored in Mongo.

Idempotent admin seeding: on startup, ensures the master admin from env exists
and that the password matches the current env value (hash is updated if env changes).
"""
import os
import uuid
import bcrypt
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel, EmailStr, Field

VALID_ROLES = {"admin", "technician", "invisacook"}


def _clean_pages(pages):
    import security
    if pages is None:
        return None
    bad = [p for p in pages if p not in security.ALL_PAGES]
    if bad:
        raise HTTPException(status_code=400, detail=f"Página inválida: {bad[0]}")
    return list(dict.fromkeys(pages))


def _check_password(pw: str):
    if len(pw or "") < 8:
        raise HTTPException(status_code=400, detail="A senha deve ter pelo menos 8 caracteres")


# ─── Pydantic models ────────────────────────────────────────────────
class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str = "technician"
    phone: Optional[str] = None
    active: bool = True
    pages: Optional[List[str]] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None  # if provided, re-hashes
    role: Optional[str] = None
    phone: Optional[str] = None
    active: Optional[bool] = None
    pages: Optional[List[str]] = None
    reset_pages: bool = False


class UserPublic(BaseModel):
    id: str
    name: str
    email: str
    role: str
    phone: Optional[str] = None
    active: bool
    created_at: Optional[str] = None


# ─── Password helpers ───────────────────────────────────────────────
def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _fernet():
    import base64
    import hashlib
    from cryptography.fernet import Fernet
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(os.environ["JWT_SECRET"].encode()).digest()))


def encrypt_password(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_password(token: Optional[str]) -> str:
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8") if token else ""
    except Exception:
        return ""


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ─── DB helpers (Mongo) ─────────────────────────────────────────────
def _public(doc: dict) -> dict:
    import security
    return {
        "id": doc.get("id"),
        "name": doc.get("name", ""),
        "email": doc.get("email", ""),
        "role": doc.get("role", "technician"),
        "phone": doc.get("phone") or None,
        "active": doc.get("active", True),
        "created_at": doc.get("created_at"),
        "pages": security.pages_of(doc, doc.get("role", "technician"), doc.get("email", "")),
        "custom_pages": doc.get("pages") is not None,
    }


async def find_user_by_email(mongo_db, email: str) -> Optional[dict]:
    user = await mongo_db["users"].find_one({"email": (email or "").strip().lower()}, {"_id": 0})
    return user


async def seed_admin(mongo_db):
    """Ensure the legacy/master admin exists and password matches env."""
    admin_email = (os.environ.get("APP_LOGIN_EMAIL") or "").strip().lower()
    admin_password = os.environ.get("APP_LOGIN_PASSWORD") or ""
    if not admin_email or not admin_password:
        return
    existing = await mongo_db["users"].find_one({"email": admin_email})
    now = datetime.now(timezone.utc).isoformat()
    if existing is None:
        await mongo_db["users"].insert_one({
            "id": str(uuid.uuid4()),
            "name": "Administrador",
            "email": admin_email,
            "password_hash": hash_password(admin_password),
            "password_enc": encrypt_password(admin_password),
            "role": "admin",
            "phone": None,
            "active": True,
            "created_at": now,
        })
    else:
        updates = {}
        if existing.get("role") != "admin":
            updates["role"] = "admin"
        if not existing.get("password_hash") or not verify_password(admin_password, existing.get("password_hash", "")):
            updates["password_hash"] = hash_password(admin_password)
        if decrypt_password(existing.get("password_enc")) != admin_password:
            updates["password_enc"] = encrypt_password(admin_password)
        if updates:
            await mongo_db["users"].update_one({"_id": existing["_id"]}, {"$set": updates})

    # Unique index on email (idempotent)
    try:
        await mongo_db["users"].create_index("email", unique=True)
    except Exception:
        pass


def setup_users_routes(api_router, mongo_db, verify_token):
    """Register /api/users routes. Admin-only for write operations."""

    async def _require_admin(payload: dict = Depends(verify_token)):
        if payload.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Acesso restrito a administradores")
        return payload

    @api_router.get("/users")
    async def list_users(_: dict = Depends(_require_admin)):
        cursor = mongo_db["users"].find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1)
        rows = await cursor.to_list(length=500)
        return [{**_public(r), "password": decrypt_password(r.get("password_enc"))} for r in rows]

    @api_router.post("/users")
    async def create_user(body: UserCreate, request: Request, admin: dict = Depends(_require_admin)):
        import security
        email = body.email.strip().lower()
        _check_password(body.password)
        if body.role not in VALID_ROLES:
            raise HTTPException(status_code=400, detail="Role inválido")
        existing = await mongo_db["users"].find_one({"email": email})
        if existing:
            raise HTTPException(status_code=400, detail="Já existe um usuário com este email")
        doc = {
            "id": str(uuid.uuid4()),
            "name": body.name.strip(),
            "email": email,
            "password_hash": hash_password(body.password),
            "password_enc": encrypt_password(body.password),
            "role": body.role,
            "phone": body.phone,
            "active": body.active,
            "pages": _clean_pages(body.pages),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await mongo_db["users"].insert_one(doc)
        await security.event("user_created", request, by=admin.get("email"), target=email, role=body.role)
        return _public(doc)

    @api_router.put("/users/{user_id}")
    async def update_user(user_id: str, body: UserUpdate, request: Request, admin: dict = Depends(_require_admin)):
        import security
        existing = await mongo_db["users"].find_one({"id": user_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")
        updates = {}
        if body.name is not None:
            updates["name"] = body.name.strip()
        if body.email is not None:
            email = body.email.strip().lower()
            if email != existing.get("email"):
                clash = await mongo_db["users"].find_one({"email": email})
                if clash:
                    raise HTTPException(status_code=400, detail="Email já em uso")
            updates["email"] = email
        if body.password:
            _check_password(body.password)
            updates["password_hash"] = hash_password(body.password)
            updates["password_enc"] = encrypt_password(body.password)
            updates["tokens_valid_after"] = int(datetime.now(timezone.utc).timestamp())
        if body.role is not None:
            if body.role not in VALID_ROLES:
                raise HTTPException(status_code=400, detail="Role inválido")
            # Cannot demote the master admin
            if existing.get("email") == (os.environ.get("APP_LOGIN_EMAIL") or "").strip().lower() and body.role != "admin":
                raise HTTPException(status_code=400, detail="Não é permitido alterar o role do admin principal")
            updates["role"] = body.role
        if body.phone is not None:
            updates["phone"] = body.phone
        if body.active is not None:
            if existing.get("email") == (os.environ.get("APP_LOGIN_EMAIL") or "").strip().lower() and not body.active:
                raise HTTPException(status_code=400, detail="Não é permitido desativar o admin principal")
            updates["active"] = body.active
            if not body.active:
                updates["tokens_valid_after"] = int(datetime.now(timezone.utc).timestamp())
        if body.reset_pages:
            updates["pages"] = None
        elif body.pages is not None:
            updates["pages"] = _clean_pages(body.pages)
        if updates:
            await mongo_db["users"].update_one({"id": user_id}, {"$set": updates})
            security.forget_user(existing.get("email"))
            security.forget_user(updates.get("email"))
            await security.event("user_updated", request, by=admin.get("email"), target=existing.get("email"),
                                 fields=sorted(k for k in updates if k not in ("password_hash", "password_enc")))
        updated = await mongo_db["users"].find_one({"id": user_id})
        return _public(updated)

    @api_router.delete("/users/{user_id}")
    async def delete_user(user_id: str, request: Request, admin: dict = Depends(_require_admin)):
        import security
        existing = await mongo_db["users"].find_one({"id": user_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")
        if existing.get("email") == (os.environ.get("APP_LOGIN_EMAIL") or "").strip().lower():
            raise HTTPException(status_code=400, detail="Não é permitido excluir o admin principal")
        await mongo_db["users"].delete_one({"id": user_id})
        security.forget_user(existing.get("email"))
        await security.event("user_deleted", request, by=admin.get("email"), target=existing.get("email"))
        return {"ok": True}

    # Public-ish for techs: list active technicians (admin only — used in admin UI assigning OS)
    @api_router.get("/users/technicians")
    async def list_technicians(_: dict = Depends(verify_token)):
        cursor = mongo_db["users"].find(
            {"role": "technician", "active": True},
            {"_id": 0, "password_hash": 0}
        ).sort("name", 1)
        rows = await cursor.to_list(length=500)
        return [_public(r) for r in rows]
