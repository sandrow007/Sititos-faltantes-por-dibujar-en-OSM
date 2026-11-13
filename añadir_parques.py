# -*- coding: utf-8 -*-
"""Descarga parques y jardines de OpenStreetMap (Overpass API) para el termino
de Mairena del Aljarafe y los guarda en mairena_parques.json (FeatureCollection).

No modifica mairena_datos.json ni ningun otro archivo: solo crea este nuevo.
"""
import json
import math
import os
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
DATOS = os.path.join(AQUI, "mairena_datos.json")
SALIDA = os.path.join(AQUI, "mairena_parques.json")

OVERPASS = "https://overpass-api.de/api/interpreter"


def area_poligono(ring):
    a = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i]
        x2, y2 = ring[i + 1]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0


def main():
    with open(DATOS, encoding="utf-8") as f:
        datos = json.load(f)

    ring = datos["boundary"]["coordinates"][0]
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    bbox = (min(lats), min(lons), max(lats), max(lons))
    bbox_str = "{},{},{},{}".format(*bbox)

    query = """[out:json][timeout:90];
(
  way["leisure"~"^(park|garden)$"](%f,%f,%f,%f);
  relation["leisure"~"^(park|garden)$"](%f,%f,%f,%f);
);
out geom tags;
""" % (bbox + bbox)

    print("Consultando Overpass API...")
    req = urllib.request.Request(
        OVERPASS, data=query.encode("utf-8"),
        headers={"User-Agent": "mairena-osm-huecos/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        osm = json.load(r)

    features = []
    for el in osm.get("elements", []):
        tags = el.get("tags", {}) or {}
        nombre = tags.get("name") or "Zona verde"
        tipo = "parque" if tags.get("leisure") == "park" else "jardin"

        if el["type"] == "way":
            coords = [[p["lon"], p["lat"]] for p in el.get("geometry", [])]
            if len(coords) < 4 or coords[0] != coords[-1]:
                continue
            geom = {"type": "Polygon", "coordinates": [coords]}
        elif el["type"] == "relation":
            anillos = []
            for m in el.get("members", []):
                if m.get("role") in ("outer", "") and m.get("type") == "way" and "geometry" in m:
                    c = [[p["lon"], p["lat"]] for p in m["geometry"]]
                    if len(c) >= 4:
                        anillos.append(c)
            if not anillos:
                continue
            geom = {"type": "MultiPolygon",
                    "coordinates": [[c] for c in anillos]}
        else:
            continue

        coords = geom["coordinates"]
        if geom["type"] == "Polygon":
            sup = area_poligono(coords[0])
        else:
            sup = sum(area_poligono(p[0]) for p in coords)
        # metros cuadrados aproximados (grados -> m con lat media)
        latm = math.radians(sum(p[1] for p in coords[0]) / len(coords[0]))
        sup_m2 = sup * (111320.0 ** 2) * math.cos(latm)

        props = {"n": nombre, "t": tipo, "s": round(sup_m2)}
        features.append({"type": "Feature",
                         "geometry": geom,
                         "properties": props})

    features.sort(key=lambda f: -f["properties"]["s"])
    with open(SALIDA, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features},
                  f, ensure_ascii=False, separators=(",", ":"))
    print("Guardados %d parques/jardines en %s" % (len(features), SALIDA))


if __name__ == "__main__":
    main()
