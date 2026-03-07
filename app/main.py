from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import io
import os
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAPBOX_TOKEN = os.getenv("MAPBOX_TOKEN")
TILE_SIZE = 256

def decode_terrain_rgb(r: int, g: int, b: int) -> float:
    return -10000 + ((r * 256 * 256 + g * 256 + b) * 0.1)

@app.get("/")
def root():
    return {"status": "flood engine running"}

@app.get("/flood/{level}/{z}/{x}/{y}.png")
def flood_tile(level: int, z: int, x: int, y: int):
    if not MAPBOX_TOKEN:
        raise HTTPException(status_code=500, detail="Missing MAPBOX_TOKEN")

    terrain_url = (
        f"https://api.mapbox.com/v4/mapbox.terrain-rgb/{z}/{x}/{y}.pngraw"
        f"?access_token={MAPBOX_TOKEN}"
    )

    resp = requests.get(terrain_url, timeout=20)
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Could not fetch terrain tile: {resp.status_code}"
        )

    terrain_img = Image.open(io.BytesIO(resp.content)).convert("RGB")
    terrain_pixels = terrain_img.load()

    out = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
    out_pixels = out.load()

    for px in range(TILE_SIZE):
        for py in range(TILE_SIZE):
            r, g, b = terrain_pixels[px, py]
            elevation = decode_terrain_rgb(r, g, b)

            if elevation <= level:
                depth = level - elevation

                if depth > 500:
                    color = (30, 64, 175, 210)
                elif depth > 100:
                    color = (29, 78, 216, 190)
                elif depth > 20:
                    color = (37, 99, 235, 170)
                elif depth > 5:
                    color = (59, 130, 246, 155)
                else:
                    color = (56, 189, 248, 140)

                out_pixels[px, py] = color

    buffer = io.BytesIO()
    out.save(buffer, format="PNG")

    return Response(
        content=buffer.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )
