from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import io

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

TILE_SIZE = 256

@app.get("/")
def root():
    return {"status": "flood engine running"}

@app.get("/flood/{level}/{z}/{x}/{y}.png")
def flood_tile(level: int, z: int, x: int, y: int):
    img = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (180, 180, 180, 255))
    pixels = img.load()

    threshold = level % 256

    for i in range(TILE_SIZE):
        for j in range(TILE_SIZE):
            value = (i + j + x * 3 + y * 7 + z * 5) % 256
            if value < threshold:
                pixels[i, j] = (40, 120, 255, 180)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")

    return Response(
        content=buffer.getvalue(),
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=3600"
        },
    )
