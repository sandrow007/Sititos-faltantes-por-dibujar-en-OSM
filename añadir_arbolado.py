#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convierte el inventario de arbolado y parques del Ayto. de Mairena
(shapefile ETRS89 / UTM 29N) a WGS84 y lo cruza contra mairena_datos.json:

- Duplicados: los árboles oficiales que ya existen en OSM (capa "trees",
  radio de tolerancia) se marcan como ya mapeados y NO se añaden.
- Puntos sobre edificios: los árboles cuyo punto cae dentro de un polígono
  de edificio (OSM 3D/2D) también se descartan.
- Los árboles "Sin arbol" del inventario (alcorques vacíos) se sacan como
  capa propia "alcorques".

Salida: mairena_datos.json con dos claves nuevas:
  - arbolado_oficial  : features GeoJSON de árboles nuevos (no en OSM)
  - alcorques_vacios  : puntos de alcorques sin árbol

Uso: python añadir_arbolado.py
"""
import json
import os
import sys

import geopandas as gpd
from shapely.geometry import Point, shape

AQUI = os.path.dirname(os.path.abspath(__file__))
DATOS = os.path.join(AQUI, "mairena_datos.json")
SHP = r"C:\Users\SANDR\Downloads\Arboles_Parques_Mairena\Arbolado_Mairena.shp"

# Tolerancia para considerar un árbol oficial igual a uno de OSM (metros)
TOLERANCIA_M = 15.0


def main():
    print("Leyendo " + SHP)
    arbolado = gpd.read_file(SHP)
    print("CRS original: " + str(arbolado.crs))
    arbolado = arbolado.to_crs(epsg=4326)
    limites = json.load(open(DATOS, encoding="utf-8"))

    # Árboles OSM ya presentes
    arboles_osm = [Point(lon, lat) for lat, lon in limites.get("trees", [])]

    # Edificios OSM (3D + 2D) para descartar puntos que caen dentro
    edificios = [shape(f["geometry"]) for f in limites.get("buildings3d", [])]
    edificios += [shape(f["geometry"]) for f in limites.get("buildings2d", [])]

    # geopandas usa sindex: preparamos un GeoSeries para consultas espaciales
    gs_osm = gpd.GeoSeries(arboles_osm, crs="EPSG:4326")
    gs_edif = gpd.GeoSeries(edificios, crs="EPSG:4326")

    # Conversión de tolerancia metros->grados (aprox a esta latitud)
    import math
    lat0 = 37.35
    dlat = TOLERANCIA_M / 111320.0
    dlon = TOLERANCIA_M / (111320.0 * math.cos(math.radians(lat0)))

    arbolado_oficial = []
    alcorques = []
    n_dupe = 0
    n_edificio = 0

    # Índice espacial de OSM para dedupe rápido
    osm_buffered = gs_osm.buffer(0.00001)  # base, usamos distancia manual

    osm_coords = [(p.y, p.x) for p in arboles_osm]
    sindex = gs_osm.sindex

    for _, fila in arbolado.iterrows():
        pt = fila.geometry
        if pt is None or pt.is_empty:
            continue
        lon, lat = pt.x, pt.y
        especie = str(fila.get("ESPECIE_2", "") or "").strip()
        nombre = str(fila.get("NOMBRE_COM", "") or "").strip()
        barrio = str(fila.get("BARRIO", "") or "").strip()
        calle = str(fila.get("CALLE", "") or "").strip()
        copa = fila.get("COPA__M_PE")
        try:
            copa = round(float(copa), 1) if copa is not None and copa == copa else None
        except (TypeError, ValueError):
            copa = None

        es_vacio = nombre.lower().startswith("sin arbol") or especie.lower().startswith("sin arbol")

        # --- ¿ya está en OSM? ---
        candidatas = list(sindex.query(pt.buffer(max(dlat, dlon))))
        ya_osm = False
        for i in candidatas:
            oy, ox = osm_coords[i]
            if abs(oy - lat) <= dlat and abs(ox - lon) <= dlon:
                ya_osm = True
                break

        # --- ¿cae sobre un edificio? ---
        sobre_edif = False
        if not ya_osm and len(gs_edif):
            cand_e = list(gs_edif.sindex.query(pt))
            for i in cand_e:
                if gs_edif.iloc[i].covers(pt):
                    sobre_edif = True
                    break

        if ya_osm:
            n_dupe += 1
            continue
        if sobre_edif:
            n_edificio += 1
            continue

        props = {"e": especie, "n": nombre}
        if barrio:
            props["b"] = barrio
        if calle:
            props["c"] = calle
        if copa is not None:
            props["copa"] = copa

        registro = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
            "properties": props,
        }
        if es_vacio:
            alcorques.append(registro)
        else:
            arbolado_oficial.append(registro)

    print("Arboles oficiales ya en OSM (descartados): " + str(n_dupe))
    print("Arboles oficiales sobre edificios (descartados): " + str(n_edificio))
    print("Arboles oficiales nuevos: " + str(len(arbolado_oficial)))
    print("Alcorques vacios: " + str(len(alcorques)))

    limites["arbolado_oficial"] = arbolado_oficial
    limites["alcorques_vacios"] = alcorques

    with open(DATOS, "w", encoding="utf-8") as f:
        json.dump(limites, f, ensure_ascii=False)
    print("Guardado " + DATOS)


if __name__ == "__main__":
    sys.exit(main())
