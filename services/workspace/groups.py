"""Shared document groups backed by the existing document engine's tags."""
import asyncio
from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

class GroupBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=100)

def register(api, identity, require_write, paperless, db, audit):
    lock = asyncio.Lock()

    def group(value):
        return {key: value[key] for key in ('id', 'name', 'document_count') if key in value}

    def name(body):
        value = body.name.strip()
        if not value or any(ord(c)<32 for c in value):
            raise HTTPException(422, 'Enter a group name without control characters')
        return value

    @api.get('/groups')
    async def list_groups(page: int = Query(1, ge=1), actor=Depends(identity)):
        value = (await paperless('GET', 'tags/', params={'page':page,'page_size':100,'ordering':'name'})).json()
        return {'count':value['count'], 'results':[group(v) for v in value['results']], 'next':page+1 if value.get('next') else None}

    @api.post('/groups', status_code=201)
    async def create_group(body: GroupBody, actor=Depends(identity)):
        require_write(actor)
        value = (await paperless('POST','tags/',json={'name':name(body),'matching_algorithm':0,'is_inbox_tag':False})).json()
        with db() as c:
            audit(c,actor,'group.create',value['id'])
        return group(value)

    @api.patch('/groups/{group_id}')
    async def rename_group(group_id: int, body: GroupBody, actor=Depends(identity)):
        require_write(actor)
        value = (await paperless('PATCH',f'tags/{group_id}/',json={'name':name(body)})).json()
        with db() as c:
            audit(c,actor,'group.rename',group_id)
        return group(value)

    async def membership(group_id, document_id, actor, add):
        require_write(actor)
        # Add/remove operations preserve other memberships. The application runs
        # one worker; serialize its read-modify-write calls to the private engine.
        async with lock:
            await paperless('GET',f'tags/{group_id}/')
            document = (await paperless('GET',f'documents/{document_id}/')).json()
            before = set(document.get('tags', []))
            after = before | {group_id} if add else before - {group_id}
            if before != after:
                document = (await paperless('PATCH',f'documents/{document_id}/',json={'tags':sorted(after)})).json()
                with db() as c:
                    audit(c,actor,'group.add_document' if add else 'group.remove_document',document_id,{'group_id':group_id})
            return document

    @api.post('/groups/{group_id}/documents/{document_id}')
    async def add_document(group_id: int, document_id: int, actor=Depends(identity)):
        return await membership(group_id, document_id, actor, True)

    @api.delete('/groups/{group_id}/documents/{document_id}')
    async def remove_document(group_id: int, document_id: int, actor=Depends(identity)):
        return await membership(group_id, document_id, actor, False)
