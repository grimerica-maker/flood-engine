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
    lat = max(min(lat, 85.05112878), -85.05112878)
    lat_rad = math.radians(lat)
    n = 2.0 ** z
    xtile = (lng + 180.0) / 360.0 * n
    ytile = ((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0) * n
    return xtile, ytile


def pixel_to_lnglat(z: int, x: int, y: int, px: int, py: int):
    n = 2.0 ** z
    lng = ((x + (px / TILE_SIZE)) / n) * 360.0 - 180.0
    merc_y = math.pi * (1 - 2 * (y + (py / TILE_SIZE)) / n)
    lat = math.degrees(math.atan(math.sinh(merc_y)))
    return lng, lat


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    earth_radius_m = 6371008.8

    lat1_rad = math.radians(lat1)
    lng1_rad = math.radians(lng1)
    lat2_rad = math.radians(lat2)
    lng2_rad = math.radians(lng2)

    dlat = lat2_rad - lat1_rad
    dlng = lng2_rad - lng1_rad

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return earth_radius_m * c


def fetch_terrain_tile(z: int, x: int, y: int) -> Image.Image:
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

    return Image.open(io.BytesIO(resp.content)).convert("RGB")


def get_elevation_at_latlng(lat: float, lng: float, z: int = 14) -> float:
    xtile_f, ytile_f = lnglat_to_tile(lng, lat, z)

    x = int(xtile_f)
    y = int(ytile_f)

    px = int((xtile_f - x) * TILE_SIZE)
    py = int((ytile_f - y) * TILE_SIZE)

    px = max(0, min(TILE_SIZE - 1, px))
    py = max(0, min(TILE_SIZE - 1, py))

    img = fetch_terrain_tile(z, x, y)
    r, g, b = img.getpixel((px, py))
    return decode_terrain_rgb(r, g, b)


def build_empty_tile() -> bytes:
    out = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
    buffer = io.BytesIO()
    out.save(buffer, format="PNG")
    return buffer.getvalue()


@app.get("/")
def root():
    return {"status": "flood engine running"}


@app.get("/elevation")
def elevation(lat: float, lng: float):
    elev = get_elevation_at_latlng(lat, lng)

    return {
        "lat": lat,
        "lng": lng,
        "elevation_m": round(elev, 2),
    }


@app.get("/flood/{level}/{z}/{x}/{y}.png")
def flood_tile(level: int, z: int, x: int, y: int):
    terrain_img = fetch_terrain_tile(z, x, y)
    terrain_pixels = terrain_img.load()

    out = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
    out_pixels = out.load()

    for px in range(TILE_SIZE):
        for py in range(TILE_SIZE):
            r, g, b = terrain_pixels[px, py]
            elev = decode_terrain_rgb(r, g, b)

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


@app.get("/impact-flood/{lat}/{lng}/{diameter}/{z}/{x}/{y}.png")
def impact_flood_tile(
    lat: float,
    lng: float,
    diameter: float,
    z: int,
    x: int,
    y: int,
):
    if diameter <= 0:
        raise HTTPException(status_code=400, detail="diameter must be > 0")

    terrain_img = fetch_terrain_tile(z, x, y)
    terrain_pixels = terrain_img.load()

    out = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
    out_pixels = out.load()

    crater_radius_m = max(500.0, diameter * 40.0)
    wave_radius_m = max(20000.0, diameter * 1200.0)
    inundation_radius_m = max(15000.0, diameter * 900.0)

    impact_elevation = get_elevation_at_latlng(lat, lng)

    for px in range(TILE_SIZE):
        for py in range(TILE_SIZE):
            sample_lng, sample_lat = pixel_to_lnglat(z, x, y, px, py)
            distance_m = haversine_m(lat, lng, sample_lat, sample_lng)

            r, g, b = terrain_pixels[px, py]
            elev = decode_terrain_rgb(r, g, b)

            # Crater / blast core
            if distance_m <= crater_radius_m:
                if elev >= -50:
                    out_pixels[px, py] = (127, 29, 29, 210)
                else:
                    out_pixels[px, py] = (153, 27, 27, 180)
                continue

            # Ocean tsunami field
            if elev < 0 and distance_m <= wave_radius_m:
                strength = 1.0 - (distance_m / wave_radius_m)
                alpha = int(40 + strength * 140)
                out_pixels[px, py] = (14, 116, 144, alpha)
                continue

            # Coastal inundation on land / shallow coast
            if distance_m <= inundation_radius_m and elev >= -10:
                wave_height_m = (diameter * 10.0) * (
                    1.0 - (distance_m / inundation_radius_m)
                )

                if wave_height_m <= 0:
                    continue

                depth = wave_height_m - max(elev, 0)

                if depth <= 0:
                    continue

                if depth > 200:
                    color = (8, 47, 73, 220)
                elif depth > 50:
                    color = (3, 105, 161, 210)
                elif depth > 10:
                    color = (2, 132, 199, 195)
                elif depth > 2:
                    color = (56, 189, 248, 180)
                else:
                    color = (125, 211, 252, 160)

                out_pixels[px, py] = color

    # If land impact, suppress open-ocean tsunami field but still allow crater core.
    if impact_elevation > 0:
        land_out = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
        land_pixels = land_out.load()

        for px in range(TILE_SIZE):
            for py in range(TILE_SIZE):
                sample_lng, sample_lat = pixel_to_lnglat(z, x, y, px, py)
                distance_m = haversine_m(lat, lng, sample_lat, sample_lng)

                r, g, b = terrain_pixels[px, py]
                elev = decode_terrain_rgb(r, g, b)

                if distance_m <= crater_radius_m:
                    if elev >= -50:
                        land_pixels[px, py] = (127, 29, 29, 210)
                    else:
                        land_pixels[px, py] = (153, 27, 27, 180)

        out = land_out

    buffer = io.BytesIO()
    out.save(buffer, format="PNG")

    return Response(
        content=buffer.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )
