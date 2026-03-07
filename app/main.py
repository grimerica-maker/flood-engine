from fastapi import FastAPI
from fastapi.responses import Response
from PIL import Image
import numpy as np
import io

app = FastAPI()

TILE_SIZE = 256

@app.get("/")
def root():
    return {"status": "flood engine running"}

@app.get("/flood/{level}/{z}/{x}/{y}.png")
def flood_tile(level: int, z: int, x: int, y: int):

    # create empty tile
    img = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (0,0,0,0))
    pixels = img.load()

    # fake flood demo pattern for now
    threshold = level % 256

    for i in range(TILE_SIZE):
        for j in range(TILE_SIZE):

            value = (i + j + x*3 + y*7 + z*5) % 256

            if value < threshold:
                pixels[i,j] = (40,120,255,180)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")

    return Response(
        content=buffer.getvalue(),
        media_type="image/png"
    )
