from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from osgeo import gdal, ogr, osr


ROAD_SHP = Path("upload/Road.shp")
REF_TIF = Path("upload/2605260200.tif")
PNG_OUT = Path("upload/road_overlay.png")
TIF_OUT = Path("upload/road_overlay.tif")
RESOLUTION_SCALE = 6
FILL_RGBA = (24, 28, 36, 120)
OUTLINE_RGBA = (8, 10, 14, 185)
OUTLINE_WIDTH = 2


def load_reference():
    ds = gdal.Open(str(REF_TIF))
    if ds is None:
        raise SystemExit(f"Cannot open reference tif: {REF_TIF}")
    gt = ds.GetGeoTransform()
    proj = ds.GetProjection()
    width = ds.RasterXSize * RESOLUTION_SCALE
    height = ds.RasterYSize * RESOLUTION_SCALE
    xmin = gt[0]
    ymax = gt[3]
    xmax = gt[0] + gt[1] * ds.RasterXSize
    ymin = gt[3] + gt[5] * ds.RasterYSize
    scaled_gt = (
        gt[0],
        gt[1] / RESOLUTION_SCALE,
        gt[2],
        gt[3],
        gt[4],
        gt[5] / RESOLUTION_SCALE,
    )
    return {
        "width": width,
        "height": height,
        "xmin": xmin,
        "ymin": ymin,
        "xmax": xmax,
        "ymax": ymax,
        "gt": scaled_gt,
        "proj": proj,
    }


def lonlat_to_pixel(lon: float, lat: float, ref: dict[str, float]) -> tuple[float, float]:
    x = (lon - ref["xmin"]) / (ref["xmax"] - ref["xmin"]) * (ref["width"] - 1)
    y = (ref["ymax"] - lat) / (ref["ymax"] - ref["ymin"]) * (ref["height"] - 1)
    return x, y


def ring_to_pixels(ring: ogr.Geometry, ref: dict[str, float]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for idx in range(ring.GetPointCount()):
        lon, lat, _ = ring.GetPoint(idx)
        points.append(lonlat_to_pixel(lon, lat, ref))
    return points


def get_transform(layer: ogr.Layer):
    src = layer.GetSpatialRef()
    if src is None:
        raise SystemExit("Road shapefile is missing spatial reference")
    src = src.Clone()
    src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    dst = osr.SpatialReference()
    dst.ImportFromEPSG(4326)
    dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return osr.CoordinateTransformation(src, dst)


def geom_bounds(geom: ogr.Geometry) -> tuple[float, float, float, float]:
    minx, maxx, miny, maxy = geom.GetEnvelope()
    return minx, miny, maxx, maxy


def intersects_ref(bounds: tuple[float, float, float, float], ref: dict[str, float]) -> bool:
    minx, miny, maxx, maxy = bounds
    return not (
        maxx < ref["xmin"] or
        minx > ref["xmax"] or
        maxy < ref["ymin"] or
        miny > ref["ymax"]
    )


def draw_polygon(draw: ImageDraw.ImageDraw, polygon: ogr.Geometry, ref: dict[str, float]):
    if polygon.GetGeometryName().upper() != "POLYGON":
        return
    outer = polygon.GetGeometryRef(0)
    if outer is None or outer.GetPointCount() < 3:
        return
    outer_pixels = ring_to_pixels(outer, ref)
    draw.polygon(outer_pixels, fill=FILL_RGBA, outline=OUTLINE_RGBA)
    if OUTLINE_WIDTH > 1:
        draw.line(outer_pixels, fill=OUTLINE_RGBA, width=OUTLINE_WIDTH, joint="curve")
    for ring_idx in range(1, polygon.GetGeometryCount()):
        hole = polygon.GetGeometryRef(ring_idx)
        if hole is None or hole.GetPointCount() < 3:
            continue
        hole_pixels = ring_to_pixels(hole, ref)
        draw.polygon(hole_pixels, fill=(0, 0, 0, 0))


def render_png(ref: dict[str, float]):
    ds = ogr.Open(str(ROAD_SHP))
    if ds is None:
        raise SystemExit(f"Cannot open road shapefile: {ROAD_SHP}")
    layer = ds.GetLayer(0)
    transform = get_transform(layer)

    image = Image.new("RGBA", (ref["width"], ref["height"]), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image, "RGBA")
    count = 0

    layer.ResetReading()
    for feature in layer:
        geom = feature.GetGeometryRef()
        if geom is None:
            continue
        geom = geom.Clone()
        geom.Transform(transform)
        if not intersects_ref(geom_bounds(geom), ref):
            continue
        name = geom.GetGeometryName().upper()
        if name == "POLYGON":
            draw_polygon(draw, geom, ref)
            count += 1
        elif name == "MULTIPOLYGON":
            for idx in range(geom.GetGeometryCount()):
                draw_polygon(draw, geom.GetGeometryRef(idx), ref)
                count += 1

    image.save(PNG_OUT)
    print(f"Rendered {count} road polygons")
    return image


def render_tif(ref: dict[str, float], image: Image.Image):
    arr = np.array(image, dtype=np.uint8)
    driver = gdal.GetDriverByName("GTiff")
    ds = driver.Create(
        str(TIF_OUT),
        ref["width"],
        ref["height"],
        4,
        gdal.GDT_Byte,
        options=["COMPRESS=DEFLATE", "PREDICTOR=2"],
    )
    ds.SetGeoTransform(ref["gt"])
    ds.SetProjection(ref["proj"])
    for band_idx in range(4):
        band = ds.GetRasterBand(band_idx + 1)
        band.WriteArray(arr[:, :, band_idx])
    ds.FlushCache()
    ds = None


def main():
    ref = load_reference()
    image = render_png(ref)
    render_tif(ref, image)
    print(PNG_OUT)
    print(TIF_OUT)


if __name__ == "__main__":
    main()
