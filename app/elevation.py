import math

# Temporary placeholder sampler
# Later this will read ETOPO tiles

def sample_elevation(lat: float, lng: float) -> float:
    """
    Returns approximate elevation.
    Placeholder until ETOPO dataset is wired.
    """

    # Very rough ocean depth approximation
    # Just so cursor works correctly for now

    if abs(lat) < 60 and abs(lng) < 180:
        if lat > 0:
            return -2000
        else:
            return -1500

    return 500
