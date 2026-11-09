#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compara los edificios OFICIALES del Catastro (INSPIRE BU) con los de OSM
y genera la lista de edificios reales que NO estan mapeados en OSM.

Salida: mairena_catastro_faltan.json (FeatureCollection en WGS84)
"""
import json
import os
import re
import sys

import pyproj
from lxml import etree
from shapely.geometry import Polygon, mapping, shape
from shapely.ops import unary_union, transform
from shapely.strtree import STRtree

AQUI = os.path.dirname(os.path.abspath(__file__))
GML = os.path.join(AQUI, "catastro_bu_41059", "A.ES.SDGC.BU.41059.building.gml")
DATOS = os.path.join(AQUI, "mairena_datos.json")
SALIDA = os.path.join(AQUI, "mairena_catastro_todos.json")

UMBRAL_COBERTURA = 0.25  # si OSM cubre >=25% del edificio catastral, se considera mapeado

transformador = pyproj.Transformer.from_crs("EPSG:25829", "EPSG:4326", always_xy=True).transform


def poligono_desde_poslist(texto):
    nums = [float(v) for v in texto.split()]
    coords = list(zip(nums[0::2], nums[1::2]))
    if len(coords) < 4:
        return None
    return Polygon(coords)


def cargar_catastro():
    print("Parseando GML del Catastro (puede tardar un par de minutos)...")
    contexto = etree.iterparse(GML, events=("end",), tag="{http://inspire.jrc.ec.europa.eu/schemas/bu-ext2d/2.0}Building", huge_tree=True)
    edificios = []
    for _, building in contexto:
        refcat = None
        ref = building.find(".//{http://inspire.jrc.ec.europa.eu/schemas/bu-core2d/2.0}reference")
        if ref is not None and ref.text:
            refcat = ref.text.strip()
        poligonos = []
        for poslist in building.iter("{http://www.opengis.net/gml/3.2}posList"):
            texto = poslist.text or ""
            try:
                poligono = poligono_desde_poslist(texto)
            except ValueError:
                continue
            if poligono is not None and poligono.is_valid and poligono.area > 0:
                poligonos.append(poligono)
        if poligonos:
            edificios.append((refcat, poligonos))
        building.clear()
        while building.getprevious() is not None:
            del building.getparent()[0]
    print("   edificios catastrales: " + str(len(edificios)))
    return edificios


def main():
    with open(DATOS, encoding="utf-8") as f:
        datos = json.load(f)
    osm_geoms = []
    for nombre in ("buildings3d", "buildings2d"):
        for fgeo in datos.get(nombre, []):
            g = shape(fgeo["geometry"])
            if not g.is_empty and g.area > 0:
                osm_geoms.append(g)
    print("Edificios OSM: " + str(len(osm_geoms)))
    arbol = STRtree(osm_geoms)

    catastro = cargar_catastro()

    faltan = []
    mapeados_list = []
    mapeados = 0
    for n, (refcat, poligonos) in enumerate(catastro):
        try:
            union = unary_union(poligonos)
            union_wgs = transform(transformador, union)
        except Exception:
            continue
        if union_wgs.is_empty or union_wgs.area <= 0:
            continue
        candidatos = arbol.query(union_wgs)
        cubierto = False
        for idx in candidatos:
            inter = union_wgs.intersection(osm_geoms[idx]).area
            if inter / union_wgs.area >= UMBRAL_COBERTURA:
                cubierto = True
                break
        if cubierto:
            mapeados += 1
        simple = union_wgs.simplify(0.3 / 111320.0, preserve_topology=True)
        g = mapping(simple)
        def red(v):
            if isinstance(v, (tuple, list)):
                if len(v) >= 2 and isinstance(v[0], (int, float)):
                    return [round(v[0], 6), round(v[1], 6)]
                return [red(x) for x in v]
            return v
        g["coordinates"] = red(g["coordinates"])
        item = {"type": "Feature", "geometry": g, "properties": {"r": refcat or "", "m": 1 if cubierto else 0}}
        (mapeados_list if cubierto else faltan).append(item)
        if (n + 1) % 2000 == 0:
            print("   " + str(n + 1) + "/" + str(len(catastro)))

    print("Mapeados en OSM: " + str(mapeados))
    print("Edificios oficiales SIN mapear: " + str(len(faltan)))

    coleccion = {"type": "FeatureCollection", "features": mapeados_list + faltan}
    with open(SALIDA, "w", encoding="utf-8") as f:
        json.dump(coleccion, f, ensure_ascii=False, separators=(",", ":"))
    print("Guardado: " + SALIDA + " (" + format(os.path.getsize(SALIDA) / 1048576, ".2f") + " MB)")


if __name__ == "__main__":
    main()
