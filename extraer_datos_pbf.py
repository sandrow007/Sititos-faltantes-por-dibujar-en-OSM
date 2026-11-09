#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extrae los datos de Mairena del Aljarafe desde un .osm.pbf de Geofabrik
y los guarda en mairena_datos.json para que HuecosMairena.py funcione 100% offline.

Uso: python extraer_datos_pbf.py [ruta_al_pbf]
Salida: mairena_datos.json
"""
import json
import os
import sys

import pyrosm
from shapely.geometry import mapping, Point, Polygon

AQUI = os.path.dirname(os.path.abspath(__file__))
PBF = sys.argv[1] if len(sys.argv) > 1 else os.path.join(AQUI, "andalucia-latest.osm.pbf")
SALIDA = os.path.join(AQUI, "mairena_datos.json")
MUNICIPIO = "Mairena del Aljarafe"


def redondear(value):
    if isinstance(value, (tuple, list)):
        if len(value) >= 2 and isinstance(value[0], (int, float)) and isinstance(value[1], (int, float)):
            return [round(value[0], 6), round(value[1], 6)]
        return [redondear(item) for item in value]
    return value


def geometria_json(geom):
    simple = geom.simplify(0.5 / 111320.0, preserve_topology=True)
    result = mapping(simple)
    result["coordinates"] = redondear(result["coordinates"])
    return result


def feature(geom, properties=None):
    return {"type": "Feature", "geometry": geometria_json(geom), "properties": properties or {}}


def anillo_exterior(geom):
    if geom.geom_type == "Polygon":
        return list(geom.exterior.coords)
    if geom.geom_type == "MultiPolygon":
        return list(geom.geoms[0].exterior.coords)
    return None


def main():
    if not os.path.exists(PBF):
        sys.exit("No existe el PBF: " + PBF)
    print("Abriendo " + os.path.basename(PBF) + " (" + format(os.path.getsize(PBF) / 1048576, ".0f") + " MB)...")
    osm = pyrosm.OSM(PBF)
    print("Buscando el limite municipal de " + MUNICIPIO + "...")
    limites = osm.get_boundaries(boundary_type="administrative", name=MUNICIPIO)
    if limites is None or len(limites) == 0:
        # pyrosm no filtra por nombre de forma fiable; probamos con todos los admin.
        limites = osm.get_boundaries(boundary_type="administrative")
        limites = limites[limites["name"] == MUNICIPIO]
    if limites is None or len(limites) == 0:
        sys.exit("No encontre el limite de " + MUNICIPIO + " en el PBF.")
    if "admin_level" in limites.columns:
        try:
            limites = limites[limites["admin_level"].astype(str) == "8"]
        except Exception:
            pass
    boundary = limites.geometry.unary_union
    print("   limites: " + str([round(v, 4) for v in boundary.bounds]))

    print("Extrayendo barrios (place=suburb/neighbourhood/quarter)...")
    places = osm.get_pois(custom_filter={"place": ["suburb", "neighbourhood", "quarter"]})
    neighbourhoods = []
    if places is not None and len(places):
        for _, row in places.iterrows():
            nombre = row.get("name")
            if not isinstance(nombre, str) or not nombre:
                continue
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            point = geom if geom.geom_type == "Point" else geom.representative_point()
            neighbourhoods.append({"name": nombre, "lat": float(point.y), "lon": float(point.x), "place": row.get("place")})
    print("   " + str(len(neighbourhoods)) + " barrios")

    print("Extrayendo suelo residencial (landuse=residential)...")
    resid = osm.get_landuse(custom_filter={"landuse": ["residential"]})
    residential = []
    if resid is not None and len(resid):
        for _, row in resid.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            geom = geom.intersection(boundary)
            if not geom.is_empty:
                residential.append(geometria_json(geom))
                nombre = row.get("name")
                if isinstance(nombre, str) and nombre and all(n["name"] != nombre for n in neighbourhoods):
                    point = geom.representative_point()
                    neighbourhoods.append({"name": nombre, "lat": float(point.y), "lon": float(point.x), "place": "residential"})
    print("   " + str(len(residential)) + " areas residenciales")

    print("Extrayendo edificios (building / building:part)...")
    bld = osm.get_buildings()
    buildings3d, buildings2d = [], []
    if bld is not None and len(bld):
        cols = bld.columns
        for _, row in bld.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            geom = geom.intersection(boundary)
            if geom.is_empty or geom.area == 0:
                continue
            if geom.geom_type not in ("Polygon", "MultiPolygon"):
                continue
            geom = geom.simplify(0.5 / 111320.0, preserve_topology=True)
            es_3d = False
            for col in ("height", "building:levels", "building:height"):
                if col in cols:
                    valor = row.get(col)
                    if valor is not None and str(valor).strip() not in ("", "nan", "None"):
                        es_3d = True
                        break
            (buildings3d if es_3d else buildings2d).append(feature(geom))
    print("   " + str(len(buildings3d) + len(buildings2d)) + " edificios (" + str(len(buildings3d)) + " con altura)")

    print("Extrayendo arboles (natural=tree)...")
    arboles_df = osm.get_pois(custom_filter={"natural": ["tree"]})
    trees = []
    if arboles_df is not None and len(arboles_df):
        for _, row in arboles_df.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            point = geom if geom.geom_type == "Point" else geom.representative_point()
            trees.append([float(point.y), float(point.x)])
    print("   " + str(len(trees)) + " arboles")

    datos = {
        "boundary": geometria_json(boundary),
        "neighbourhoods": neighbourhoods,
        "residential": residential,
        "buildings3d": buildings3d,
        "buildings2d": buildings2d,
        "trees": trees,
    }
    with open(SALIDA, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False)
    print("Guardado: " + SALIDA + " (" + format(os.path.getsize(SALIDA) / 1048576, ".1f") + " MB)")


if __name__ == "__main__":
    main()