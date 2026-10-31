"""Derive what clients may see about a plane from the round-target rule.

The hint comes from ``resolve_round_target``, the same rule both selectPlane
handlers apply, so a plane is ``eligible`` exactly when the server would accept
it for a round.
"""

from backend.schemas.plane import PlaneState, PublicPlaneState, RouteHint
from backend.services.round_target import RouteProblem, resolve_round_target

_PUBLIC_FIELDS = set(PublicPlaneState.model_fields) - {"route_hint"}


def route_hint_for(
    origin: str | None, destination: str | None, monitored_airport: str
) -> RouteHint:
    """Return the route hint for a plane flying ``origin`` -> ``destination``.

    A plane that does not touch the monitored airport gets an empty hint, so an
    overflight reveals neither end of its route.
    """
    target = resolve_round_target(origin, destination, monitored_airport)
    if target.problem is RouteProblem.NOT_MONITORED:
        return RouteHint(guess_direction=None, known_airport=None, eligible=False)
    return RouteHint(
        guess_direction=target.guess_direction,
        known_airport=monitored_airport,
        eligible=target.is_playable,
    )


def to_public_plane(plane: PlaneState, monitored_airport: str) -> PublicPlaneState:
    """Project an ingested plane onto the fields clients may receive, plus its route hint."""
    return PublicPlaneState(
        **plane.model_dump(include=_PUBLIC_FIELDS),
        route_hint=route_hint_for(plane.origin, plane.destination, monitored_airport),
    )
