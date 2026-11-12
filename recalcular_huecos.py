#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Recalcula los huecos usando el CATASTRO OFICIAL como fuente de verdad:

- Un cuadrado solo es "hueco de edificios" si el Catastro confirma edificios
  en esa celda que OSM no tiene mapeados.
- Incrusta tambien la capa catbuildings (edificios oficiales sin mapear)
  con sus popups, dentro de mairena_osm_huecos.html.
- Suma al recuento de arboles por celda el arbolado oficial del Ayto.
  (arbolado_oficial) y lleva cuenta aparte de alcorques vacios
  (alcorques_vacios), incrustando ambas capas en el HTML.

Uso: python recalcular_huecos.py
"""
import html
import json
import math
import os
from shapely.geometry import Point, box, shape
from shapely.ops import unary_union

AQUI = os.path.dirname(os.path.abspath(__file__))
DATOS = os.path.join(AQUI, "mairena_datos.json")
ROADS = os.path.join(AQUI, "mairena_roads.json")
CATASTRO = os.path.join(AQUI, "mairena_catastro_todos.json")
HTML = os.path.join(AQUI, "mairena_osm_huecos.html")

CELDA_M = 200
MIN_URBANO = 0.10
MIN_CALLES_M = 120.0
MIN_COBERTURA_EDIF = 0.15     # cobertura maxima de OSM para considerar hueco
MIN_CATASTRO_M2 = 300.0       # el Catastro debe confirmar >=300 m2 de edificio
MIN_RATIO_3D = 0.50
MIN_ARBOLES_HA = 8.0


def redondear(value):
    if isinstance(value, (tuple, list)):
        if len(value) >= 2 and isinstance(value[0], (int, float)) and isinstance(value[1], (int, float)):
            return [round(value[0], 6), round(value[1], 6)]
        return [redondear(item) for item in value]
    return value


def geometria_json(geom):
    from shapely.geometry import mapping
    simple = geom.simplify(0.5 / 111320.0, preserve_topology=True)
    result = mapping(simple)
    result["coordinates"] = redondear(result["coordinates"])
    return result


def feature(geom, properties=None):
    return {"type": "Feature", "geometry": geometria_json(geom), "properties": properties or {}}


def popup_catastro(f):
    ref = (f.get("properties") or {}).get("r", "")
    coords = f["geometry"]["coordinates"]
    anillo = coords[0] if f["geometry"]["type"] == "Polygon" else (coords[0][0] if coords and coords[0] else [[0, 0]])
    lon0, lat0 = anillo[0][0], anillo[0][1]
    partes = ['<b>Edificio oficial sin mapear en OSM</b>']
    if len(ref) >= 14:
        enlace = 'https://www1.sedecatastro.gob.es/CYCBienInmueble/OVCListaBienes.aspx?rc1=' + ref[:7] + '&rc2=' + ref[7:]
        partes.append('Ref. Catastro: ' + html.escape(ref))
        partes.append('<a href="' + enlace + '">Ficha del Catastro</a>')
    partes.append('<a href="https://www.openstreetmap.org/edit?editor=id#map=19/' + format(lat0, ".6f") + '/' + format(lon0, ".6f") + '">Editar en iD</a>')
    return '<br>'.join(partes)


def stat_nueva():
    return {"area": 0.0, "n": 0, "n3": 0, "trees": 0, "roads": 0.0, "cat": 0.0, "catn": 0, "ofic": 0, "alq": 0}


def main():
    with open(DATOS, encoding="utf-8") as f:
        datos = json.load(f)
    with open(ROADS, encoding="utf-8") as f:
        roads = json.load(f)
    with open(CATASTRO, encoding="utf-8") as f:
        catastro = json.load(f)

    boundary = shape(datos["boundary"])
    if not boundary.is_valid:
        boundary = boundary.buffer(0)

    barrios = []
    priority = {"town": 4, "quarter": 3, "suburb": 2, "neighbourhood": 1, "residential": 1}
    for item in datos.get("neighbourhoods", []):
        punto = Point(item["lon"], item["lat"])
        if boundary.covers(punto):
            barrios.append({"name": item["name"], "lat": item["lat"], "lon": item["lon"],
                            "area": priority.get(item.get("place"), 1) * 1000000})

    residential = [shape(g) for g in datos.get("residential", [])]
    residential_union = unary_union(residential) if residential else boundary

    coslat = math.cos(math.radians((boundary.bounds[1] + boundary.bounds[3]) / 2))
    m2 = (111320.0 ** 2) * coslat
    minx, miny, maxx, maxy = boundary.bounds
    dy = CELDA_M / 111320.0
    dx = dy / coslat

    def cell_key(lat, lon):
        return int((lon - minx) / dx), int((lat - miny) / dy)

    def barrio_cercano(lat, lon):
        if not barrios:
            return "(sin barrio)"
        return min(barrios, key=lambda b: (lat - b["lat"]) ** 2 + ((lon - b["lon"]) * coslat) ** 2)["name"]

    cell_stats = {}
    n_edif = 0
    for nombre in ("buildings3d", "buildings2d"):
        es_3d = nombre == "buildings3d"
        for fgeo in datos.get(nombre, []):
            geom = shape(fgeo["geometry"])
            if geom.is_empty or geom.area == 0:
                continue
            centro = geom.centroid
            stat = cell_stats.setdefault(cell_key(centro.y, centro.x), stat_nueva())
            stat["area"] += geom.area * m2
            stat["n"] += 1
            if es_3d:
                stat["n3"] += 1
            n_edif += 1
    print("Edificios OSM: " + str(n_edif))

    # CATASTRO OFICIAL: area confirmada por celda
    n_cat = 0
    for fgeo in catastro.get("features", []):
        geom = shape(fgeo["geometry"])
        if geom.is_empty or geom.area == 0:
            continue
        centro = geom.centroid
        stat = cell_stats.setdefault(cell_key(centro.y, centro.x), stat_nueva())
        stat["cat"] += geom.area * m2
        stat["catn"] += 1
        n_cat += 1
    print("Edificios Catastro: " + str(n_cat))

    n_arb = 0
    for lat, lon in datos.get("trees", []):
        if not boundary.covers(Point(lon, lat)):
            continue
        cell_stats.setdefault(cell_key(lat, lon), stat_nueva())["trees"] += 1
        n_arb += 1
    print("Arboles: " + str(n_arb))

    # ARBOLADO OFICIAL del Ayto. (solo lo no mapeado en OSM): cuenta como
    # arbol a efectos de huecos de arbolado, con contador propio.
    n_ofic = 0
    for fgeo in datos.get("arbolado_oficial", []):
        lon, lat = fgeo["geometry"]["coordinates"]
        if not boundary.covers(Point(lon, lat)):
            continue
        stat = cell_stats.setdefault(cell_key(lat, lon), stat_nueva())
        stat["trees"] += 1
        stat["ofic"] += 1
        n_ofic += 1
    print("Arboles oficiales nuevos: " + str(n_ofic))

    # ALCORQUES VACIOS del inventario municipal: contador propio por celda.
    n_alq = 0
    for fgeo in datos.get("alcorques_vacios", []):
        lon, lat = fgeo["geometry"]["coordinates"]
        if not boundary.covers(Point(lon, lat)):
            continue
        cell_stats.setdefault(cell_key(lat, lon), stat_nueva())["alq"] += 1
        n_alq += 1
    print("Alcorques vacios: " + str(n_alq))

    n_vias = 0
    for fgeo in roads.get("features", []):
        geom = shape(fgeo["geometry"])
        if geom.is_empty:
            continue
        longitud_m = geom.length * 111320.0 * coslat
        celdas_tocadas = set()
        for dist in (0.0, 0.33, 0.66, 1.0):
            p = geom.interpolate(dist, normalized=True)
            celdas_tocadas.add(cell_key(p.y, p.x))
        for clave in celdas_tocadas:
            cell_stats.setdefault(clave, stat_nueva())["roads"] += longitud_m / max(1, len(celdas_tocadas))
        n_vias += 1
    print("Vias: " + str(n_vias))

    gaps, gaps3d, gaptrees = [], [], []
    nx, ny = int(math.ceil((maxx - minx) / dx)), int(math.ceil((maxy - miny) / dy))
    for i in range(nx):
        for j in range(ny):
            celda = box(minx + i * dx, miny + j * dy, minx + (i + 1) * dx, miny + (j + 1) * dy).intersection(boundary)
            if celda.is_empty or celda.area < 0.1 * dx * dy:
                continue
            stat = cell_stats.get((i, j), stat_nueva())
            urbano = celda.intersection(residential_union)
            es_urbano = urbano.area / celda.area >= MIN_URBANO or stat["roads"] >= MIN_CALLES_M
            if not es_urbano:
                continue
            area_urbana = urbano.area * m2
            cobertura = stat["area"] / area_urbana if area_urbana else 0.0
            arboles_ha = stat["trees"] / (area_urbana / 10000.0) if area_urbana else 0.0
            centro = celda.representative_point()
            nombre = barrio_cercano(centro.y, centro.x)
            info = ("<b>" + html.escape(nombre) + "</b><br>Edificios OSM: " + str(stat["n"]) + " (con altura: " + str(stat["n3"]) + ")<br>"
                    + "Edificios Catastro: " + str(stat["catn"]) + " (" + format(stat["cat"], ".0f") + " m2)<br>"
                    + "Cobertura OSM: " + format(cobertura, ".0%") + "<br>Arboles: " + str(stat["trees"]) + " (" + format(arboles_ha, ".1f") + "/ha)"
                    + " [oficiales nuevos: " + str(stat["ofic"]) + "]<br>Alcorques vacios: " + str(stat["alq"]) + "<br>"
                    + '<a href="https://www.openstreetmap.org/edit?editor=id#map=18/' + format(centro.y, ".6f") + "/" + format(centro.x, ".6f") + '">Editar en iD</a>')
            item = feature(celda, {"i": info, "b": nombre})
            # HUECO REAL: OSM escaso Y Catastro confirma edificios
            if stat["cat"] >= MIN_CATASTRO_M2 and cobertura < MIN_COBERTURA_EDIF:
                gaps.append(item)
            elif stat["n"] and stat["n3"] / stat["n"] < MIN_RATIO_3D:
                gaps3d.append(item)
            if arboles_ha < MIN_ARBOLES_HA:
                gaptrees.append(item)

    print("Huecos: " + str(len(gaps)) + " edificios (Catastro), " + str(len(gaps3d)) + " alturas, " + str(len(gaptrees)) + " arboles")

    # Capa de edificios oficiales sin mapear (con popups)
    catbuildings = []
    n_sin = 0
    for fgeo in catastro.get("features", []):
        if (fgeo.get("properties") or {}).get("m"):
            continue
        fgeo["properties"]["i"] = popup_catastro(fgeo)
        catbuildings.append(fgeo)
        n_sin += 1
    print("Catastro sin OSM: " + str(n_sin))

    with open(HTML, encoding="utf-8") as f:
        pagina = f.read()
    tag = '<script id="map-data" type="application/json">'
    ini = pagina.index(tag) + len(tag)
    fin = pagina.index("</script>", ini)
    data = json.loads(pagina[ini:fin])
    data["gaps"] = gaps
    data["gaps3d"] = gaps3d
    data["gaptrees"] = gaptrees
    data["catbuildings"] = catbuildings
    # Capas nuevas del arbolado oficial del Ayto. y alcorques vacios
    data["arbolado_oficial"] = datos.get("arbolado_oficial", [])
    data["alcorques_vacios"] = datos.get("alcorques_vacios", [])
    nuevo = json.dumps(data, ensure_ascii=False)
    with open(HTML, "w", encoding="utf-8") as f:
        f.write(pagina[:ini] + nuevo + pagina[fin:])
    print("HTML actualizado: " + HTML)


if __name__ == "__main__":
    main()
