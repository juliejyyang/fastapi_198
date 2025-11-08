from fastapi import FastAPI
from fastapi.responses import StreamingResponse, HTMLResponse
import asyncio
from contextlib import asynccontextmanager
import serial

arduino_connection = None 

# ------- SERIAL READINGS ------- #
@asynccontextmanager
async def app_lifespan(app: FastAPI):
    global arduino_connection
    arduino_connection = serial.Serial(
        port='/dev/cu.usbmodem101', 
        baudrate=9600, 
        timeout=1
    )
    await asyncio.sleep(2) 
    yield
    if arduino_connection and arduino_connection.is_open:
        arduino_connection.close()

# ------ APP STUFF OR WHATEVA... ------ #
app = FastAPI(lifespan = app_lifespan) #pass app_lifespan to FastAPI

@app.get('/', response_class=HTMLResponse)
async def get_home():
    with open('test.html', 'r') as f:
        return f.read()

@app.get('/stream') # create an endpoint to get a continous datastream from arduino serial output
async def serial_stream():
    async def generate():
        while True:
            if arduino_connection and arduino_connection.in_waiting:
                data = await asyncio.to_thread(
                    lambda: arduino_connection.readline().decode('utf-8').strip()
                )
                yield f"data: {data}\n\n"
            await asyncio.sleep(0.1)
    return StreamingResponse(generate(), media_type="text/event-stream")
