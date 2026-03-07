from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import io
import os
import requests
from collections import deque

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
META_SIZE = TILE_SIZE * 3


def decode_terrain_rgb(r: int, g: int, b: int) -> float:
    return -10000 + ((r * 256 * 256 + g * 256 + b) * 0.1)


def fetch_terrain_tile(z: int, x: int, y: int) -> Image.Image:
    max_index = (2 ** z) - 1

    # wrap x horizontally
    x = x % (2 ** z)

    # clamp y vertically
    if y < 0 or y > max_index:
        return Image.new("RGB", (TILE_SIZE, TILE_SIZE), (0, 0, 0))

    terrain_url = (
        f"https://api.mapbox.com/v4/mapbox.terrain-rgb/{z}/{x}/{y}.pngraw"
        f"?access_token={MAPBOX_TOKEN}"
    )

    resp = requests.get(terrain_url, timeout=20)
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Could not fetch terrain tile {z}/{x}/{y}: {resp.status_code}",
        )

    return Image.open(io.BytesIO(resp.content)).convert("RGB")


def build_meta_tile(z: int, x: int, y: int) -> Image.Image:
    meta = Image.new("RGB", (META_SIZE, META_SIZE))

    for dy in range(-1, 2):
        for dx in range(-1, 2):
            tile = fetch_terrain_tile(z, x + dx, y + dy)
            paste_x = (dx + 1) * TILE_SIZE
            paste_y = (dy + 1) * TILE_SIZE
            meta.paste(tile, (paste_x, paste_y))

    return meta


def ocean_connected_mask(elevations, sea_level):
    """
    Flood only cells:
    1. below or equal to sea_level
    2. connected to present-day ocean (elevation <= 0)
    """
    h = len(elevations)
    w = len(elevations[0])

    passable = [[False] * w for _ in range(h)]
    flooded = [[False] * w for _ in range(h)]
    q = deque()

    for py in range(h):
        for px in range(w):
            e = elevations[py][px]
            if e <= sea_level:
                passable[py][px] = True

    # Seed from current ocean cells on the metatile edges
    def try_seed(px, py):
        if px < 0 or px >= w or py < 0 or py >= h:
            return
        if flooded[py][px]:
            return
        if not passable[py][px]:
            return
        if elevations[py][px] > 0:
            return
        flooded[py][px] = True
        q.append((px, py))

    for px in range(w):
        try_seed(px, 0)
        try_seed(px, h - 1)

    for py in range(h):
        try_seed(0, py)
        try_seed(w - 1, py)

    directions = [
        (-1, 0), (1, 0), (0, -1), (0, 1),
        (-1, -1), (1, -1), (-1, 1), (1, 1),
    ]

    while q:
        px, py = q.popleft()

        for dx, dy in directions:
            nx = px + dx
            ny = py + dy

            if nx < 0 or nx >= w or ny < 0 or ny >= h:
                continue
            if flooded[ny][nx]:
                continue
            if not passable[ny][nx]:
                continue

            flooded[ny][nx] = True
            q.append((nx, ny))

    return flooded


@app.get("/")
def root():
    return {"status": "flood engine running"}


@app.get("/flood/{level}/{z}/{x}/{y}.png")
def flood_tile(level: int, z: int, x: int, y: int):
    if not MAPBOX_TOKEN:
        raise HTTPException(status_code=500, detail="Missing MAPBOX_TOKEN")

    meta_img = build_meta_tile(z, x, y)
    meta_pixels = meta_img.load()

    elevations = []
    for py in range(META_SIZE):
        row = []
        for px in range(META_SIZE):
            r, g, b = meta_pixels[px, py]
            row.append(decode_terrain_rgb(r, g, b))
        elevations.append(row)

    out = Image.new("RGBA", (META_SIZE, META_SIZE), (0, 0, 0, 0))
    out_pixels = out.load()

    # Positive sea level: ocean-connected flooding
    if level >= 0:
        flooded = ocean_connected_mask(elevations, level)

        for py in range(META_SIZE):
            for px in range(META_SIZE):
                if not flooded[py][px]:
                    continue

                elevation = elevations[py][px]
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

    # Negative sea level: exposed seafloor between new sea level and 0 m
    else:
        for py in range(META_SIZE):
            for px in range(META_SIZE):
                elevation = elevations[py][px]

                if level <= elevation <= 0:
                    height_above_new_sea = elevation - level

                    if height_above_new_sea > 500:
                        color = (120, 74, 34, 210)
                    elif height_above_new_sea > 100:
                        color = (160, 110, 60, 190)
                    elif height_above_new_sea > 20:
                        color = (194, 145, 82, 175)
                    elif height_above_new_sea > 5:
                        color = (222, 179, 107, 160)
                    else:
                        color = (240, 211, 155, 145)

                    out_pixels[px, py] = color

    # Crop center tile out of the 3x3 metatile
    cropped = out.crop((TILE_SIZE, TILE_SIZE, TILE_SIZE * 2, TILE_SIZE * 2))

    buffer = io.BytesIO()
    cropped.save(buffer, format="PNG")

    return Response(
        content=buffer.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )
