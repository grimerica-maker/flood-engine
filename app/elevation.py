@app.get("/elevation")
def elevation(lat: float, lng: float):
    if not MAPBOX_TOKEN:
        raise HTTPException(status_code=500, detail="Missing MAPBOX_TOKEN")

    def lnglat_to_tile(lng: float, lat: float, z: int):
        lat_rad = math.radians(lat)
        n = 2.0 ** z
        xtile = (lng + 180.0) / 360.0 * n
        ytile = ((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0) * n
        return xtile, ytile

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
