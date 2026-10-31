"""Truck distances (A9): real road km from OSRM, or straight line x circuity for comparison."""
import numpy as np

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle km; works elementwise on scalars or broadcastable arrays."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(np.asarray(lon2) - np.asarray(lon1))
    h = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(h))


def straight_km_matrix(a, b, circuity: float) -> np.ndarray:
    """len(a) x len(b) straight-line km x circuity between two frames with lat/lon columns."""
    return circuity * haversine_km(a.lat.to_numpy()[:, None], a.lon.to_numpy()[:, None],
                                   b.lat.to_numpy()[None, :], b.lon.to_numpy()[None, :])


_networks = {}


def road_km_matrix(a, b, cfg) -> np.ndarray:
    """len(a) x len(b) truck km, by the method in cfg['roads']['source']. inf = no road route."""
    if cfg["roads"]["source"] == "haversine":
        return straight_km_matrix(a, b, cfg["circuity"])
    from src.roads import RoadNetwork
    k = (cfg["roads"]["matrix_cache"], cfg["circuity"])
    if k not in _networks:
        _networks[k] = RoadNetwork(cfg)
    return _networks[k].matrix(a, b)
