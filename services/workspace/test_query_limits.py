"""Isolated API checks: synthetic HTTP transport, no production files or records."""
import asyncio
import gzip
import unittest
from unittest.mock import patch
import httpx
from fastapi import HTTPException
import app as workspace
from query_limits import QueryBudget, plain_search

class QueryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        workspace.QUERY_BUDGET.history.clear()
        workspace.QUERY_BUDGET.cooldown_until=0
        self.requests=[]
        async def upstream(request):
            self.requests.append(request)
            page=int(request.url.params.get('page',1))
            size=int(request.url.params.get('page_size',30))
            rows=[{'id':i,'title':'Synthetic document','added':'2026-09-24','original_file_name':'example.txt','tags':[],'content':'Never in list responses'} for i in range(65,0,-1)]
            return httpx.Response(200,json={'count':len(rows),'next':'upstream' if page*size<len(rows) else None,'previous':'upstream' if page>1 else None,'results':rows[(page-1)*size:page*size]})
        self.upstream=httpx.AsyncClient(transport=httpx.MockTransport(upstream))
        workspace.app.state.http=self.upstream
        self.headers=patch.object(workspace,'paperless_headers',return_value={})
        self.headers.start()
        workspace.app.dependency_overrides[workspace.identity]=lambda:{'username':'synthetic','scope':'read'}
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=workspace.app),base_url='http://workspace.test')

    async def asyncTearDown(self):
        workspace.app.dependency_overrides.clear()
        self.headers.stop()
        await self.client.aclose()
        await self.upstream.aclose()

    async def test_pagination_metadata_and_filter(self):
        ids=[]
        for page,length in [(1,30),(2,30),(3,5)]:
            response=await self.client.get('/api/v1/documents',params={'page':page,'group_id':7})
            self.assertEqual(response.status_code,200)
            data=response.json()
            self.assertEqual(len(data['results']),length)
            self.assertEqual(data['next'],page+1 if page<3 else None)
            self.assertEqual(data['previous'],page-1 if page>1 else None)
            self.assertTrue(all('content' not in row for row in data['results']))
            ids.extend(row['id'] for row in data['results'])
        self.assertEqual(len(set(ids)),65)
        for request in self.requests:
            self.assertEqual(request.url.params['fields'],'id,title,original_file_name,added,tags')
            self.assertEqual(request.url.params['tags__id'],'7')
            self.assertEqual(request.url.params['ordering'],'-id')

    async def test_invalid_queries_never_reach_engine(self):
        for params in [{'page':0},{'page':1001},{'page_size':31},{'page_size':0},{'q':'x'*201},{'q':'*'},{'q':'title:secret'},{'q':'word '*13}]:
            response=await self.client.get('/api/v1/documents',params=params)
            self.assertEqual(response.status_code,422,params)
        self.assertEqual(self.requests,[])
        for params in [{'page':1001},{'page_size':100000},{'q':'x'*101}]:
            self.assertEqual((await self.client.get('/api/v1/groups',params=params)).status_code,422)
        self.assertEqual(self.requests,[])

    async def test_rate_limit_covers_browser_and_agent_routes(self):
        for i in range(60):
            response=await self.client.get(('/api/v1' if i%2 else '/ui-api')+'/documents')
            self.assertEqual(response.status_code,200)
        response=await self.client.get('/api/v1/documents')
        self.assertEqual(response.status_code,429)
        self.assertIn('retry-after',response.headers)
        self.assertEqual(len(self.requests),60)

    async def test_concurrency_fails_fast_and_recovers(self):
        budget=QueryBudget()
        async with budget.admit('one'):
            async with budget.admit('two'):
                with self.assertRaises(HTTPException) as error:
                    async with budget.admit('three'):pass
                self.assertEqual(error.exception.status_code,429)
        async with budget.admit('three'):pass

    async def test_response_bytes_are_bounded(self):
        async def oversized(request):return httpx.Response(200,content=b'x'*2048)
        async with httpx.AsyncClient(transport=httpx.MockTransport(oversized)) as client:
            workspace.app.state.http=client
            with self.assertRaises(HTTPException) as error:
                await workspace.paperless('GET','documents/',max_bytes=1024)
            self.assertEqual(error.exception.status_code,502)

    async def test_compressed_response_is_decoded_once(self):
        async def compressed(request):return httpx.Response(200,content=gzip.compress(b'{"count":0}'),headers={'Content-Encoding':'gzip'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(compressed)) as client:
            workspace.app.state.http=client
            response=await workspace.paperless('GET','documents/',max_bytes=1024)
            self.assertEqual(response.json(),{'count':0})

    async def test_api_rejects_third_inflight_query(self):
        started=0
        ready=asyncio.Event()
        release=asyncio.Event()
        async def slow(request):
            nonlocal started
            started+=1
            if started==2:ready.set()
            await release.wait()
            return httpx.Response(200,json={'count':0,'results':[],'next':None,'previous':None})
        async with httpx.AsyncClient(transport=httpx.MockTransport(slow)) as client:
            workspace.app.state.http=client
            pending=[asyncio.create_task(self.client.get('/api/v1/documents')) for _ in range(2)]
            try:
                await asyncio.wait_for(ready.wait(),2)
                response=await asyncio.wait_for(self.client.get('/ui-api/documents'),1)
                self.assertEqual(response.status_code,429)
                self.assertEqual(started,2)
            finally:
                release.set()
                await asyncio.gather(*pending)

    async def test_timeout_opens_cooldown_then_recovers(self):
        async def slow(request):
            await asyncio.sleep(1)
            return httpx.Response(200,json={})
        budget=QueryBudget()
        async with httpx.AsyncClient(transport=httpx.MockTransport(slow)) as client:
            workspace.app.state.http=client
            with self.assertRaises(HTTPException) as error:
                async with budget.admit('one'):
                    await workspace.paperless('GET','documents/',max_bytes=1024,deadline=.01)
            self.assertEqual(error.exception.status_code,504)
        with self.assertRaises(HTTPException) as error:
            async with budget.admit('two'):pass
        self.assertEqual(error.exception.status_code,503)
        budget.cooldown_until=0
        async with budget.admit('two'):pass

    def test_search_words_are_literal(self):
        self.assertEqual(plain_search('invoice OR 2026'),'"invoice" AND "OR" AND "2026"')

if __name__=='__main__':unittest.main()
