from __future__ import annotations

import json
from pathlib import Path


TOPO_SPECS = [
    (Path("upload/taiwan-towns-63000.topo.json"), Path("upload/taiwan-towns-63000.geojson")),
    (Path("upload/taiwan-towns-65000.topo.json"), Path("upload/taiwan-towns-65000.geojson")),
]
MERGED_GEOJSON = Path("upload/taiwan-towns-combined.geojson")


def decode_arcs(topology: dict) -> list[list[list[float]]]:
    scale_x, scale_y = topology["transform"]["scale"]
    translate_x, translate_y = topology["transform"]["translate"]
    decoded = []
    for arc in topology["arcs"]:
        points = []
        x = 0
        y = 0
        for dx, dy in arc:
            x += dx
            y += dy
            points.append([
                x * scale_x + translate_x,
                y * scale_y + translate_y,
            ])
        decoded.append(points)
    return decoded


def extract_arc(arcs: list[list[list[float]]], index: int) -> list[list[float]]:
    if index >= 0:
      coords = arcs[index]
    else:
      coords = list(reversed(arcs[~index]))
    return [pt[:] for pt in coords]


def join_arc_indexes(arcs: list[list[list[float]]], indexes: list[int]) -> list[list[float]]:
    coords: list[list[float]] = []
    for index in indexes:
        arc_coords = extract_arc(arcs, index)
        if coords and arc_coords and coords[-1] == arc_coords[0]:
            coords.extend(arc_coords[1:])
        else:
            coords.extend(arc_coords)
    return coords


def geometry_to_geojson(decoded_arcs: list[list[list[float]]], geometry: dict) -> dict:
    geom_type = geometry["type"]
    if geom_type == "Polygon":
        return {
            "type": "Polygon",
            "coordinates": [join_arc_indexes(decoded_arcs, ring) for ring in geometry["arcs"]],
        }
    if geom_type == "MultiPolygon":
        return {
            "type": "MultiPolygon",
            "coordinates": [
                [join_arc_indexes(decoded_arcs, ring) for ring in polygon]
                for polygon in geometry["arcs"]
            ],
        }
    raise ValueError(f"Unsupported geometry type: {geom_type}")


def build_features(topology: dict):
    decoded_arcs = decode_arcs(topology)
    geometries = topology["objects"]["map"]["geometries"]
    features = []
    for geometry in geometries:
        features.append({
            "type": "Feature",
            "properties": geometry.get("properties", {}),
            "geometry": geometry_to_geojson(decoded_arcs, geometry),
        })
    return features


def write_geojson(path: Path, features: list[dict]):
    feature_collection = {
        "type": "FeatureCollection",
        "features": features,
    }
    path.write_text(json.dumps(feature_collection, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Exported {len(features)} features")
    print(path)


def build_geojson():
    combined_features = []
    for topo_path, out_geojson in TOPO_SPECS:
        topology = json.loads(topo_path.read_text(encoding="utf-8"))
        features = build_features(topology)
        write_geojson(out_geojson, features)
        combined_features.extend(features)
    write_geojson(MERGED_GEOJSON, combined_features)


if __name__ == "__main__":
    build_geojson()
