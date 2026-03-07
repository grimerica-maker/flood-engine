import math

def sample_elevation(lat: float, lng: float) -> float:
    if abs(lat) < 60 and abs(lng) < 180:
        if lat > 0:
            return -2000
        else:
            return -1500

    return 500
