"""Geospatial helper utilities."""

import math
from typing import Sequence, Tuple, Union

Coords = Tuple[float, float]


def haversine_km(
    *args: Union[float, Sequence[float]],
) -> float:  # pyright: ignore[reportIncompatibleParameterType]
    """Compute great-circle distance between two WGS-84 coordinates.

    This helper supports *two* calling conventions to remain backward- and
    test-compatible:

    1. ``haversine_km(lat1, lon1, lat2, lon2)`` – four individual floats.
    2. ``haversine_km((lat1, lon1), (lat2, lon2))`` – two ``(lat, lon)`` tuples.

    Args:
        *args: Either four floats *(lat1, lon1, lat2, lon2)* or two coordinate
            tuples.

    Returns:
        Distance in kilometres as a float.

    Raises:
        ValueError: If an unsupported argument signature is supplied.
    """

    if len(args) == 4:
        lat1, lon1, lat2, lon2 = args  # type: ignore[assignment]
    elif len(args) == 2:
        coord1, coord2 = args
        if (
            isinstance(coord1, Sequence)
            and isinstance(coord2, Sequence)
            and len(coord1) == 2
            and len(coord2) == 2
        ):
            lat1, lon1 = coord1  # type: ignore[misc]
            lat2, lon2 = coord2  # type: ignore[misc]
        else:
            raise ValueError(
                "When passing two arguments they must be coordinate sequences of length 2."
            )
    else:
        raise ValueError("haversine_km expects either 2 or 4 positional arguments.")

    r = 6371.0088  # Mean Earth radius (IUGG)
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c
