from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import io
import os
import requests
import math

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


def lnglat_to_tile(lng: float, lat: float, z: int):
    lat_rad = math.radians(lat)
    n = 2.0 ** z
    xtile = (lng + 180.0) / 360.0 * n
    ytile = ((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0) * n
    return xtile, ytile


@app.get("/")
def root():
    return {"status": "flood engine running"}


@app.get("/elevation")
def elevation(lat: float, lng: float):
    if not MAPBOX_TOKEN:
        raise HTTPException(status_code=500, detail="Missing MAPBOX_TOKEN")

    z = 14
    xtile_f, ytile_f = lnglat_to_tile(lng, lat, z)

    x = int(xtile_f)
    y = int(ytile_f)

    px = int((xtile_f - x) * TILE_SIZE)
    py = int((ytile_f - y) * TILE_SIZE)

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

    img = Image.open(io.BytesIO(resp.content)).convert("RGB")

    r, g, b = img.getpixel((px, py))
    elev = decode_terrain_rgb(r, g, b)

    return {
        "lat": lat,
        "lng": lng,
        "elevation_m": round(elev, 2)
    }


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
            elev = decode_terrain_rgb(r, g, b)

            # Positive sea level = flooding
            if level > 0:
                if elev <= level:
                    depth = level - elev

                    if depth > 500:
                        color = (30, 64, 175, 220)
                    elif depth > 100:
                        color = (29, 78, 216, 200)
                    elif depth > 20:
                        color = (37, 99, 235, 180)
                    elif depth > 5:
                        color = (59, 130, 246, 165)
                    else:
                        color = (56, 189, 248, 150)

                    out_pixels[px, py] = color

            # Negative sea level = drained ocean / exposed shelf
            elif level < 0:
                if level <= elev <= 0:
                    exposed = elev - level

                    if exposed > 500:
                        color = (120, 74, 34, 220)
                    elif exposed > 100:
                        color = (160, 110, 60, 200)
                    elif exposed > 20:
                        color = (194, 145, 82, 180)
                    elif exposed > 5:
                        color = (222, 179, 107, 165)
                    else:
                        color = (240, 211, 155, 150)

                    out_pixels[px, py] = color

    buffer = io.BytesIO()
    out.save(buffer, format="PNG")

    return Response(
        content=buffer.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )
