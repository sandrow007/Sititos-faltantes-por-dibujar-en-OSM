#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extrae la red viaria (highway) de Mairena del Aljarafe desde el PBF
y guarda las lineas en mairena_roads.json para incrustarlas en el mapa.

Uso: python extraer_calles_pbf.py [ruta_al_pbf]
Salida: mairena_roads.json  (FeatureCollection de LineString)
"""
import json
import os
import sys

import pyrosm
from shapely.geometry import mapping

AQUI = os.path.dirname(os.path.abspath(__file__))
PBF = sys.argv[1] if len(sys.argv) > 1 else os.path.join(AQUI, "andalucia-latest.osm.pbf")
SALIDA = os.path.join(AQUI, "mairena_roads.json")
MUNICIPIO = "Mairena del Aljarafe"

# Jerarquia viaria: "main" = avenidas/carreteras, "local" = calles
PRINCIPALES = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified"}
CALLES = {"residential", "living_street", "pedestrian", "service", "track"}


def redondear(value):
    if isinstance(value, (tuple, list)):
        if len(value) >= 2 and isinstance(value[0], (int, float)) and isinstance(value[1], (int, float)):
            return [round(value[0], 6), round(value[1], 6)]
        return [redondear(item) for item in value]
    return value


def main():
    if not os.path.exists(PBF):
        sys.exit("No existe el PBF: " + PBF)
    print("Abriendo " + os.path.basename(PBF) + "...")
    osm = pyrosm.OSM(PBF)

    print("Buscando el limite municipal...")
    limites = osm.get_boundaries(boundary_type="administrative", name=MUNICIPIO)
    if limites is None or len(limites) == 0:
        limites = osm.get_boundaries(boundary_type="administrative")
        limites = limites[limites["name"] == MUNICIPIO]
    if limites is None or len(limites) == 0:
        sys.exit("No encontre el limite de " + MUNICIPIO)
    if "admin_level" in limites.columns:
        try:
            limites = limites[limites["admin_level"].astype(str) == "8"]
        except Exception:
            pass
    boundary = limites.geometry.unary_union
    print("   limite: " + str([round(v, 4) for v in boundary.bounds]))

    print("Extrayendo vias (highway)...")
    net = osm.get_network(network_type="all")
    if net is None or len(net) == 0:
        sys.exit("No se extrajo ninguna via.")
    if "highway" in net.columns:
        net = net[net["highway"].notna()]
    net = net[net.geometry.notna() & ~net.geometry.is_empty]
    net = net[net.geometry.intersects(boundary)]
    print("   vias tocando el termino: " + str(len(net)))

    features = []
    for _, row in net.iterrows():
        tipo = str(row.get("highway") or "")
        if tipo not in PRINCIPALES and tipo not in CALLES:
            continue
        geom = row.geometry.intersection(boundary)
        if geom.is_empty:
            continue
        cls = "main" if tipo in PRINCIPALES else "local"
        nombre = row.get("name")
        props = {"cls": cls}
        if isinstance(nombre, str) and nombre:
            props["n"] = nombre
        if geom.geom_type == "LineString":
            simple = geom.simplify(1.0 / 111320.0, preserve_topology=True)
            g = mapping(simple)
            g["coordinates"] = redondear(g["coordinates"])
            features.append({"type": "Feature", "geometry": g, "properties": props})
        elif geom.geom_type == "MultiLineString":
            simple = geom.simplify(1.0 / 111320.0, preserve_topology=True)
            for coords in simple.geoms:
                g = {"type": "LineString", "coordinates": redondear(list(coords.coords))}
                features.append({"type": "Feature", "geometry": g, "properties": props})
    print("   lineas guardadas: " + str(len(features)))

    coleccion = {"type": "FeatureCollection", "features": features}
    with open(SALIDA, "w", encoding="utf-8") as f:
        json.dump(coleccion, f, ensure_ascii=False, separators=(",", ":"))
    print("Guardado: " + SALIDA + " (" + format(os.path.getsize(SALIDA) / 1048576, ".2f") + " MB)")


if __name__ == "__main__":
    main()
