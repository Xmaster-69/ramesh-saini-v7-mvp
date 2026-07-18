import aiohttp
import asyncio

async def fetch():
    async with aiohttp.ClientSession() as session:
        async with session.get("https://api.github.com") as r:
            return await r.json()