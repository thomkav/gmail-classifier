import asyncio
from fastapi import APIRouter
from pydantic import BaseModel

import llm_classifier as llm

router = APIRouter()


@router.get("/llm/status")
async def llm_status(probe: bool = True):
    return await asyncio.to_thread(llm.check_status, probe)


class ResetUnknownBody(BaseModel):
    domains: list[str] | None = None
    account_id: int | None = None


@router.post("/llm/cache/reset-unknowns")
async def reset_unknown_cache(body: ResetUnknownBody = ResetUnknownBody()):
    deleted = await asyncio.to_thread(llm.reset_unknown_cache, body.domains, body.account_id)
    return {"deleted": deleted}
