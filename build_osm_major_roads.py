from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from osgeo import gdal


RAW_PATH = Path("upload/osm_major_roads_raw.json")
REF_TIF = Path("upload/2605260200.tif")
PNG_OUT = Path("upload/osm_major_roads_overlay.png")
TIF_OUT = Path("upload/osm_major_roads_overlay.tif")


STYLE = {
    "motorway": {"outer": 8, "inner": 4, "outer_rgba": (0, 0, 0, 140), "inner_rgba": (245, 245, 245, 215)},
    "trunk": {"outer": 8, "inner": 4, "outer_rgba": (0, 0, 0, 140), "inner_rgba": (245, 245, 245, 215)},
    "primary": {"outer": 7, "inner": 3, "outer_rgba": (0, 0, 0, 128), "inner_rgba": (235, 235, 235, 205)},
    "secondary": {"outer": 5, "inner": 2, "outer_rgba": (0, 0, 0, 118), "inner_rgba": (220, 220, 220, 190)},
    "tertiary": {"outer": 3, "inner": 1, "outer_rgba": (0, 0, 0, 105), "inner_rgba": (205, 205, 205, 170)},
    "motorway_link": {"outer": 4, "inner": 2, "outer_rgba": (0, 0, 0, 118), "inner_rgba": (225, 225, 225, 195)},
    "trunk_link": {"outer": 4, "inner": 2, "outer_rgba": (0, 0, 0, 118), "inner_rgba": (225, 225, 225, 195)},
    "primary_link": {"outer": 4, "inner": 2, "outer_rgba": (0, 0, 0, 112), "inner_rgba": (220, 220, 220, 185)},
    "secondary_link": {"outer": 3, "inner": 1, "outer_rgba": (0, 0, 0, 105), "inner_rgba": (210, 210, 210, 170)},
    "tertiary_link": {"outer": 3, "inner": 1, "outer_rgba": (0, 0, 0, 105), "inner_rgba": (210, 210, 210, 170)},
}

DRAW_ORDER = [
    "tertiary",
    "tertiary_link",
    "secondary",
    "secondary_link",
    "primary",
    "primary_link",
    "trunk",
    "trunk_link",
    "motorway",
    "motorway_link",
]


def load_reference():
    ds = gdal.Open(str(REF_TIF))
    if ds is None:
        raise SystemExit(f"Cannot open reference tif: {REF_TIF}")
    gt = ds.GetGeoTransform()
    proj = ds.GetProjection()
    width = ds.RasterXSize
    height = ds.RasterYSize
    xmin = gt[0]
    ymax = gt[3]
    xmax = xmin + gt[1] * width
    ymin = ymax + gt[5] * height
    return {
        "width": width,
        "height": height,
        "xmin": xmin,
        "ymin": ymin,
        "xmax": xmax,
        "ymax": ymax,
        "gt": gt,
        "proj": proj,
    }


def lonlat_to_pixel(lon: float, lat: float, ref: dict[str, float]) -> tuple[float, float]:
    x = (lon - ref["xmin"]) / (ref["xmax"] - ref["xmin"]) * (ref["width"] - 1)
    y = (ref["ymax"] - lat) / (ref["ymax"] - ref["ymin"]) * (ref["height"] - 1)
    return x, y


def build_road_geometries(ref: dict[str, float]):
    payload = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    nodes = {}
    roads = []

    for el in payload.get("elements", []):
        if el.get("type") == "node":
            nodes[el["id"]] = (el["lon"], el["lat"])

    for el in payload.get("elements", []):
        if el.get("type") != "way":
            continue
        highway = el.get("tags", {}).get("highway")
        if highway not in STYLE:
            continue
        coords = [nodes[nid] for nid in el.get("nodes", []) if nid in nodes]
        if len(coords) < 2:
            continue
        pixels = [lonlat_to_pixel(lon, lat, ref) for lon, lat in coords]
        roads.append({"highway": highway, "pixels": pixels})
    return roads


def render_png(ref: dict[str, float], roads: list[dict[str, object]]):
    image = Image.new("RGBA", (ref["width"], ref["height"]), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image, "RGBA")

    for highway in DRAW_ORDER:
        for road in roads:
            if road["highway"] != highway:
                continue
            pixels = road["pixels"]
            style = STYLE[highway]
            draw.line(pixels, fill=style["outer_rgba"], width=style["outer"], joint="curve")
            draw.line(pixels, fill=style["inner_rgba"], width=style["inner"], joint="curve")

    image.save(PNG_OUT)
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
    if not RAW_PATH.exists():
        raise SystemExit(f"Missing raw OSM file: {RAW_PATH}")
    ref = load_reference()
    roads = build_road_geometries(ref)
    image = render_png(ref, roads)
    render_tif(ref, image)
    print(f"Rendered {len(roads)} roads")
    print(PNG_OUT)
    print(TIF_OUT)


if __name__ == "__main__":
    main()
