# gee_utils.py
"""
Google Earth Engine / Dynamic World — original-style connection:

- Annual composites (Jan 1 – Dec 31) with per-pixel ``mode()`` on ``label``.
- Regional maps: ``filterBounds(point)`` (same as your original code).
- Global Home view: annual composite without ``filterBounds`` (full-world mosaic).

Do not build ``ee.Geometry`` at module import time; only inside these functions
after ``ee.Initialize()`` has run.
"""

from datetime import date

import ee

from config import CLASS_PALETTE


def build_dynamic_world_image(point_geom: ee.Geometry, year: int):
    """
    Dynamic World land cover for one calendar year at a point (original pattern).
    """
    start = f"{year}-01-01"
    end = f"{year}-12-31"

    dw_collection = (
        ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
        .filterDate(start, end)
        .filterBounds(point_geom)
    )

    dw_image = dw_collection.select("label").mode()

    vis_params = {
        "min": 0,
        "max": 8,
        "palette": CLASS_PALETTE,
    }

    return dw_image, vis_params


def build_dynamic_world_global_year(year: int):
    """Annual global label mode (no filterBounds) — for Home / world map."""
    start = f"{year}-01-01"
    end = f"{year}-12-31"

    dw_image = (
        ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
        .filterDate(start, end)
        .select("label")
        .mode()
    )

    vis_params = {
        "min": 0,
        "max": 8,
        "palette": CLASS_PALETTE,
    }

    return dw_image, vis_params


def _image_to_tile_url(image: ee.Image, vis_params: dict) -> str | None:
    try:
        map_id = image.getMapId(vis_params)
        return map_id["tile_fetcher"].url_format
    except Exception as e:
        print("Error creating tile URL:", e)
        return None


def get_dw_tile_urls(point_geom: ee.Geometry, year_a: int, year_b: int) -> dict:
    """
    Tile URLs for year A, year B, and change layer (original pattern).
    """
    img_a, vis = build_dynamic_world_image(point_geom, year_a)
    url_a = _image_to_tile_url(img_a, vis)

    img_b, _ = build_dynamic_world_image(point_geom, year_b)
    url_b = _image_to_tile_url(img_b, vis)

    change_img = img_a.neq(img_b)
    change_vis = {"min": 0, "max": 1, "palette": ["000000", "ff0000"]}
    url_change = _image_to_tile_url(change_img, change_vis)

    return {
        "a": url_a,
        "b": url_b,
        "change": url_change,
    }


def tile_url_at_point(point_geom: ee.Geometry, year: int) -> str | None:
    """Single annual layer at a point (Home with region)."""
    img, vis = build_dynamic_world_image(point_geom, year)
    return _image_to_tile_url(img, vis)


def tile_url_global_year(year: int) -> str | None:
    """Single annual global layer (Home / world)."""
    img, vis = build_dynamic_world_global_year(year)
    return _image_to_tile_url(img, vis)
