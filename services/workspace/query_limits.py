"""Bound document/group browsing across human and machine identities."""
import asyncio
from collections import defaultdict, deque
from contextlib import asynccontextmanager
import re
import time
from fastapi import HTTPException

MAX_PAGE = 1000
MAX_PAGE_SIZE = 30
LIST_BYTES = 1024 * 1024
LIST_SECONDS = 10

def plain_search(value):
    if not value.strip():
        return ''
    if len(value)>200 or re.search(r'[*?~:{}\[\]()\\^"<>]',value):
        raise HTTPException(422, 'Use up to 200 characters of plain search words; advanced query syntax is not supported')
    words = re.findall(r'\w+', value, flags=re.UNICODE)
    if not words or len(words)>12 or any(len(word)>64 for word in words):
        raise HTTPException(422, 'Use 1–12 search words, with at most 64 characters per word')
    # Even AND/OR/NOT and field-like input are literal words, never query syntax.
    return ' AND '.join('"'+word+'"' for word in words)

class QueryBudget:
    def __init__(self):
        self.slots = asyncio.Semaphore(2)
        self.history = defaultdict(deque)
        self.cooldown_until = 0

    @asynccontextmanager
    async def admit(self, username):
        now = time.monotonic()
        for user, entries in list(self.history.items()):
            while entries and entries[0]<=now-60:
                entries.popleft()
            if not entries:
                del self.history[user]
        if now < self.cooldown_until:
            raise HTTPException(503, 'Document search is recovering; try again shortly', headers={'Retry-After':str(max(1,int(self.cooldown_until-now)+1))})
        if self.slots.locked():
            raise HTTPException(429, 'Two document queries are already running; try again shortly', headers={'Retry-After':'2'})
        entries = self.history[username]
        if len(entries)>=60:
            raise HTTPException(429, '60 document/group queries per minute per user', headers={'Retry-After':str(max(1,int(entries[0]+60-now)+1))})
        async with self.slots:
            entries.append(now)
            try:
                yield
            except HTTPException as error:
                if error.status_code==504:
                    # A client timeout does not guarantee cancellation upstream.
                    # Back off globally instead of piling retries onto that work.
                    self.cooldown_until=time.monotonic()+30
                raise
