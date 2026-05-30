import asyncio
import websockets

async def send_y():
    async with websockets.connect('ws://localhost:8000/ws') as ws:
        await ws.send('y')
        print('Sent y!')

asyncio.run(send_y())
