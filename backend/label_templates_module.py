"""
Label Templates module — CRUD para templates de adesivos térmicos.

Armazena layouts JSON serializados (compatível com fabric.js) em MongoDB
local. Templates são por usuário ou globais (criados por admin).

Schema:
  {
    id, name, width_mm, height_mm,
    layout_json: { elements: [{type, x, y, ...}] },  # fabric.js serialized
    canvas_json: <raw fabric JSON>,                   # full fabric state
    created_by, created_at, updated_at, scope
  }
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel
from fastapi import HTTPException, Depends


class LabelTemplateIn(BaseModel):
    name: str
    width_mm: float
    height_mm: float
    canvas_json: dict
    scope: str = "global"  # 'global' | 'user'


class LabelTemplate(LabelTemplateIn):
    id: str
    created_by: Optional[str] = None
    created_at: str
    updated_at: str


def _strip(doc):
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


def setup_label_templates_routes(api_router, mongo_db, verify_token):
    @api_router.get("/label-templates")
    async def list_templates(payload: dict = Depends(verify_token)):
        cursor = mongo_db["label_templates"].find({}, {"_id": 0}).sort("updated_at", -1)
        rows = await cursor.to_list(length=200)
        return rows

    @api_router.get("/label-templates/{tpl_id}")
    async def get_template(tpl_id: str, payload: dict = Depends(verify_token)):
        doc = await mongo_db["label_templates"].find_one({"id": tpl_id}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Template não encontrado")
        return doc

    @api_router.post("/label-templates")
    async def create_template(body: LabelTemplateIn, payload: dict = Depends(verify_token)):
        if payload.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Apenas admin pode criar templates")
        now = datetime.now(timezone.utc).isoformat()
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["created_by"] = payload.get("email")
        doc["created_at"] = now
        doc["updated_at"] = now
        await mongo_db["label_templates"].insert_one(doc)
        return _strip(doc)

    @api_router.put("/label-templates/{tpl_id}")
    async def update_template(tpl_id: str, body: LabelTemplateIn, payload: dict = Depends(verify_token)):
        if payload.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Apenas admin pode editar templates")
        existing = await mongo_db["label_templates"].find_one({"id": tpl_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Template não encontrado")
        updates = body.model_dump()
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await mongo_db["label_templates"].update_one({"id": tpl_id}, {"$set": updates})
        out = await mongo_db["label_templates"].find_one({"id": tpl_id}, {"_id": 0})
        return out

    @api_router.delete("/label-templates/{tpl_id}")
    async def delete_template(tpl_id: str, payload: dict = Depends(verify_token)):
        if payload.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Apenas admin pode excluir templates")
        await mongo_db["label_templates"].delete_one({"id": tpl_id})
        return {"ok": True}
