import asyncio

async def fetch_data():
    await asyncio.sleep(1)
    return {"data": "ok"}

result = asyncio.run(fetch_data())
print(result)