from __future__ import annotations

import json
from pathlib import Path

from osgeo import ogr, osr


ROAD_SHP = Path("upload/Road.shp")
OUT_GEOJSON = Path("upload/Road.geojson")


def build_geojson():
    ds = ogr.Open(str(ROAD_SHP))
    if ds is None:
        raise SystemExit(f"Cannot open shapefile: {ROAD_SHP}")
    layer = ds.GetLayer(0)

    src = layer.GetSpatialRef()
    if src is None:
        raise SystemExit("Road shapefile is missing spatial reference")
    src = src.Clone()
    src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    dst = osr.SpatialReference()
    dst.ImportFromEPSG(4326)
    dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    transform = osr.CoordinateTransformation(src, dst)

    layer_defn = layer.GetLayerDefn()
    field_names = [layer_defn.GetFieldDefn(i).GetName() for i in range(layer_defn.GetFieldCount())]

    features = []
    layer.ResetReading()
    for feature in layer:
        geom = feature.GetGeometryRef()
        if geom is None:
            continue
        geom = geom.Clone()
        geom.Transform(transform)
        geometry = json.loads(geom.ExportToJson())
        properties = {name: feature.GetField(name) for name in field_names}
        features.append({
            "type": "Feature",
            "properties": properties,
            "geometry": geometry,
        })

    fc = {"type": "FeatureCollection", "features": features}
    OUT_GEOJSON.write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Exported {len(features)} features")
    print(OUT_GEOJSON)


if __name__ == "__main__":
    build_geojson()
