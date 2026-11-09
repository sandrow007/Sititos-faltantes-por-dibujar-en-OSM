
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Huecos OSM de Mairena del Aljarafe: descarga datos y crea un HTML Leaflet 100% autonomo (sin internet).

Uso: python HuecosMairena.py
Salida: mairena_osm_huecos.html (mapa completo sin conexion) y mairena_barrios_resumen.csv
"""
import base64
import csv
import html
import json
import math
import os
import re
import sys
import time
import urllib.request
import requests
from shapely.geometry import LineString, Point, Polygon, box, mapping, shape
from shapely.ops import linemerge, polygonize, unary_union

MUNICIPIO = "Mairena del Aljarafe"
POLY_FILE = os.path.join(os.path.dirname(__file__), "mairena.poly")
SECCION_POLY = "Mairena del Aljarafe"
CELDA_M = 150          # celdas mas finas = mas huecos detectados
MIN_URBANO = 0.10      # % de suelo residencial minimo por celda
MIN_COBERTURA_EDIF = 0.15  # si la cobertura de edificios es menor, hay hueco
MIN_RATIO_3D = 0.35    # si menos del 35% de edificios tienen altura, hueco de 3D
MIN_ARBOLES_HA = 5.0
DATOS_JSON = os.path.join(os.path.dirname(__file__), "mairena_datos.json")
SALIDA_HTML = os.path.join(os.path.dirname(__file__), "mairena_osm_huecos.html")
SALIDA_CSV = os.path.join(os.path.dirname(__file__), "mairena_barrios_resumen.csv")
LEAFLET_VERSION = "1.9.4"
LEAFLET_URLS = {
    "leaflet.js": [
        "https://unpkg.com/leaflet@" + LEAFLET_VERSION + "/dist/leaflet.js",
        "https://cdn.jsdelivr.net/npm/leaflet@" + LEAFLET_VERSION + "/dist/leaflet.js",
        "https://cdnjs.cloudflare.com/ajax/libs/leaflet/" + LEAFLET_VERSION + "/leaflet.js",
    ],
    "leaflet.css": [
        "https://unpkg.com/leaflet@" + LEAFLET_VERSION + "/dist/leaflet.css",
        "https://cdn.jsdelivr.net/npm/leaflet@" + LEAFLET_VERSION + "/dist/leaflet.css",
        "https://cdnjs.cloudflare.com/ajax/libs/leaflet/" + LEAFLET_VERSION + "/leaflet.css",
    ],
}
OVERPASS = [
    "https://overpass.osm.ch/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]
OVERPASS_UA = "Mozilla/5.0 (compatible; MairenaOSMHuecos/3.0; +https://manolitoaire.com/)"
AREA = 'area["name"="' + MUNICIPIO + '"]["boundary"="administrative"]["admin_level"="8"]->.a;'
BB = "37.3168,-6.1321,37.3594,-6.0328"  # bbox aproximado del municipio, respaldo


def poligono_desde_polyfile(ruta, seccion):
    """Lee un archivo .poly (formato OSM poly) y devuelve el poligono de la seccion pedida."""
    with open(ruta, "r", encoding="utf-8") as handle:
        texto = handle.read()
    anillos, actual = {}, None
    for linea in texto.splitlines():
        parte = linea.strip()
        if not parte or parte.startswith("#"):
            continue
        if parte == "END":
            actual = None
            continue
        if actual is None:
            if parte == seccion:
                actual = seccion
            continue
        if ":" in parte and not parte[:1].isdigit() and not parte[:1] == "-":
            nombre = parte.split(":", 1)[0]
            anillos.setdefault(actual, []).append([])
            continue
        try:
            lon, lat = [float(v) for v in parte.split()[:2]]
        except (ValueError, IndexError):
            continue
        if not anillos[actual]:
            anillos[actual].append([])
        anillos[actual][-1].append((lon, lat))
    if seccion not in anillos:
        sys.exit("No encontre la seccion '" + seccion + "' en " + os.path.basename(ruta))
    anillos_seccion = [r for r in anillos[seccion] if len(r) >= 4]
    if not anillos_seccion:
        sys.exit("La seccion '" + seccion + "' no tiene anillos validos en el .poly")
    exterior = Polygon(anillos_seccion[0])
    huecos = [Polygon(r) for r in anillos_seccion[1:] if r[0] != r[-1] or Polygon(r).area > 0]
    geom = exterior
    for hueco in huecos:
        if hueco.within(exterior):
            geom = geom.difference(hueco)
    if not geom.is_valid:
        geom = geom.buffer(0)
    return unary_union([g for g in getattr(geom, "geoms", [geom]) if g.geom_type == "Polygon"])


LEAFLET_TEMPLATE = '<!doctype html>\n<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover"><meta name="apple-mobile-web-app-capable" content="yes"><title>Mairena del Aljarafe - Huecos OSM</title>\n<style>@@LEAFLET_CSS@@</style>\n<style>\n:root{color-scheme:light;--bg:#F6FAF7;--ink:#123d43;--panel:rgba(246,250,247,.96);--edge:#123d43;--gap:#E63E5F;--gap3:#FF6B1A;--tree:#FFB800;--b3:#00B98A;--b2:#667276;--gapT:#8c564b;--paper:#F6FAF7}:root[data-theme=dark]{color-scheme:dark;--bg:#03050F;--ink:#b9dddd;--panel:rgba(3,5,15,.96);--edge:#86bfc0;--gap:#FF00E5;--gap3:#FFD745;--tree:#FFD745;--b3:#00FFC8;--b2:#5B6470;--gapT:#C88A6B;--paper:#03050F}*{box-sizing:border-box}html,body,#map{width:100%;height:100%;margin:0;background:var(--bg);color:var(--ink);font-family:system-ui,-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif}body{overflow:hidden;overscroll-behavior:none}.leaflet-container{background:var(--bg);font:inherit}.leaflet-control-attribution{display:none!important}.leaflet-control-zoom a{width:42px!important;height:42px!important;line-height:40px!important;font-size:24px!important;background:var(--panel)!important;color:var(--ink)!important;border-color:var(--edge)!important}.leaflet-bar{border:1px solid var(--edge)!important;box-shadow:none!important}.topbar{position:fixed;z-index:1000;top:calc(10px + env(safe-area-inset-top));left:50%;transform:translateX(-50%);display:flex;align-items:center;gap:10px;padding:8px 12px;border:1px solid var(--edge);border-radius:14px;background:var(--panel);color:var(--ink);font-size:14px;font-weight:700;white-space:nowrap}.brand{width:44px;height:44px;border-radius:50%;background:#0b0f1a;background-image:url("@@LOGO@@");background-size:86% 86%;background-repeat:no-repeat;background-position:center;box-shadow:0 0 0 1px var(--edge)}.topbar button,.panel button{font:inherit;color:var(--ink);background:var(--bg);border:1px solid var(--edge);border-radius:9px;padding:8px 11px;min-height:40px}.panel{position:fixed;z-index:1000;right:calc(10px + env(safe-area-inset-right));top:calc(66px + env(safe-area-inset-top));width:min(280px,calc(100vw - 20px));max-height:55vh;overflow:auto;padding:9px 12px;border:1px solid var(--edge);border-radius:13px;background:var(--panel);color:var(--ink);font-size:14px}.panel summary{font-weight:700;cursor:pointer;min-height:36px;display:flex;align-items:center}.panel label{display:flex;align-items:center;gap:9px;min-height:38px;cursor:pointer}.panel input{width:21px;height:21px;accent-color:#00a890}.legend{position:fixed;z-index:1000;left:calc(10px + env(safe-area-inset-left));bottom:calc(10px + env(safe-area-inset-bottom));max-width:min(300px,calc(100vw - 20px));padding:8px 11px;border:1px solid var(--edge);border-radius:12px;background:var(--panel);color:var(--ink);font-size:12px}.legend summary{cursor:pointer;font-weight:700;min-height:30px;display:flex;align-items:center}.legend .rows{line-height:1.7}.legend .sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px}.neighbour-label{color:var(--ink);font-weight:700;text-align:center;white-space:nowrap;line-height:1.15;font-size:calc(8px + (var(--zoom,12) - 12)*.9px);-webkit-text-stroke:2px var(--bg);paint-order:stroke fill;pointer-events:none}.theme-btn{min-width:42px}.gap-badge{color:var(--gap);background:var(--bg);border:1px solid var(--gap);border-radius:4px;font-size:11px;font-weight:700;line-height:20px;height:22px;padding:0 4px;text-align:center;pointer-events:none}.leaflet-popup-content-wrapper,.leaflet-popup-tip{background:var(--panel);color:var(--ink)}.leaflet-popup-content{max-width:min(280px,70vw)}.leaflet-popup-content a{color:#007c72}.leaflet-control-container{touch-action:manipulation}@media(max-width:600px){.topbar{font-size:12px;gap:6px;padding:6px 8px}.brand{width:28px;height:28px}.panel{top:calc(66px + env(safe-area-inset-top));right:calc(10px + env(safe-area-inset-right));max-height:42vh;width:min(240px,calc(100vw - 20px))}.legend{bottom:calc(10px + env(safe-area-inset-bottom));max-width:calc(100vw - 20px)}.leaflet-control-zoom{margin-top:calc(72px + env(safe-area-inset-top))!important}}@media print{html,body,#map{height:100vh!important;background:var(--paper)!important;-webkit-print-color-adjust:exact;print-color-adjust:exact}.topbar,.panel,.leaflet-control-container,.legend summary{display:none!important}.legend{position:fixed;box-shadow:none;background:var(--paper)!important}}\n</style>\n<script>/* Leaflet 1.9.4 BSD 2-Clause License. Full license text: https://opensource.org/license/bsd-2-clause/ */</script></head>\n<body><div id="map"></div><header class="topbar"><span class="brand" aria-hidden="true"></span><span>Mairena del Aljarafe</span><button id="theme" class="theme-btn" aria-label="Cambiar tema"><svg id="icon-sun" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg><svg id="icon-moon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:none"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg></button></header><details class="panel" open><summary>Capas - <span id="zoomReadout">vista completa</span></summary><label><input type="checkbox" data-layer="gaps" checked> Huecos de edificios</label><label><input type="checkbox" data-layer="gaps3d"> Huecos de altura</label><label><input type="checkbox" data-layer="gaptrees"> Zonas con pocos arboles</label><label><input type="checkbox" data-layer="buildings3d"> Edificios con altura (zoom cercano)</label><label><input type="checkbox" data-layer="buildings2d"> Edificios sin altura (zoom cercano)</label><label><input type="checkbox" data-layer="trees"> Arboles (zoom cercano)</label><label><input type="checkbox" data-layer="labels" checked> Nombres de barrios</label><label><input type="checkbox" id="streets"> Calles (teselas enmascaradas al contorno)</label><button id="print">Imprimir</button></details><details class="legend" open><summary>Clave y datos</summary><div class="rows"><span class="sw" style="background:var(--gap)"></span>Faltan edificios<br><span class="sw" style="background:var(--gap3)"></span>Faltan alturas (3D)<br><span class="sw" style="background:var(--gapT)"></span>Pocos arboles<br><span class="sw" style="background:var(--b3)"></span>Edificio con altura<br><span class="sw" style="background:var(--b2)"></span>Edificio sin altura<br><span class="sw" style="background:var(--tree)"></span>Arbol<br><small>OpenStreetMap contributors - Leaflet 1.9.4 - solo el termino municipal</small></div></details>\n<script>@@LEAFLET_JS@@</script><script id="map-data" type="application/json">@@DATA@@</script><script>\n(function(){\'use strict\';var root=document.documentElement,theme=\'light\';\ntry{var saved=localStorage.getItem(\'mairena-theme\');if(saved===\'light\'||saved===\'dark\')theme=saved;else if(window.matchMedia&&window.matchMedia(\'(prefers-color-scheme: dark)\').matches)theme=\'dark\';}catch(e){if(window.matchMedia&&window.matchMedia(\'(prefers-color-scheme: dark)\').matches)theme=\'dark\';}\nfunction setTheme(t){theme=t;root.setAttribute(\'data-theme\',t);var sun=document.getElementById(\'icon-sun\'),moon=document.getElementById(\'icon-moon\');if(sun&&moon){sun.style.display=t===\'dark\'?\'none\':\'\';moon.style.display=t===\'dark\'?\'\':\'none\';}try{localStorage.setItem(\'mairena-theme\',t);}catch(e){}if(window.refreshMapTheme)window.refreshMapTheme();}\nsetTheme(theme);document.getElementById(\'theme\').addEventListener(\'click\',function(){setTheme(theme===\'dark\'?\'light\':\'dark\');});\nvar data=JSON.parse(document.getElementById(\'map-data\').textContent),boundary=data.boundary;\nfunction css(n){return getComputedStyle(root).getPropertyValue(n).trim();}\nfunction escapeHtml(v){return String(v).replace(/[&<>"\']/g,function(c){return{\'&\':\'&\',\'<\':\'<\',\'>\':\'>\',\'"\':\'"\',"\'":\'&#39;\'}[c];});}\nfunction ringOf(g){if(!g)return[[]];if(g.type===\'Polygon\')return g.coordinates[0];if(g.type===\'MultiPolygon\')return (g.coordinates[0]||[[]])[0];if(g.type===\'GeometryCollection\'&&g.geometries&&g.geometries.length)return ringOf(g.geometries[0]);return[[]];}\nfunction toLatLngs(r){return r.map(function(c){return[c[1],c[0]];});}\nvar shapeRing=ringOf(boundary),shapePts=toLatLngs(shapeRing),shape=L.polygon(shapePts),bounds=shape.getBounds();\nvar padLat=(bounds.getNorth()-bounds.getSouth())*.03,padLon=(bounds.getEast()-bounds.getWest())*.03;\nvar limit=L.latLngBounds([bounds.getSouth()-padLat,bounds.getWest()-padLon],[bounds.getNorth()+padLat,bounds.getEast()+padLon]);\nvar DETAIL=13;\nvar map=L.map(\'map\',{preferCanvas:true,zoomControl:true,attributionControl:false,zoomSnap:.25,zoomDelta:.5,maxZoom:19,zoomAnimation:true,markerAnimation:false,fadeAnimation:false,boxZoom:false,worldCopyJump:false,minZoom:0});\nmap.setMaxBounds(limit);\nmap.setView(bounds.getCenter(),13,{animate:false});\n[\'tiles\',\'data\',\'mask\',\'edge\'].forEach(function(n){map.createPane(n);});\nmap.getPane(\'tiles\').style.zIndex=210;map.getPane(\'data\').style.zIndex=220;map.getPane(\'mask\').style.zIndex=250;map.getPane(\'edge\').style.zIndex=260;\nmap.getPane(\'mask\').style.pointerEvents=\'none\';map.getPane(\'edge\').style.pointerEvents=\'none\';\nvar renderer=L.canvas({padding:.4,pane:\'data\'});\nvar svgRenderer=L.svg({pane:\'mask\'});\nvar bb=bounds.pad(1);var world=[[bb.getNorth(),bb.getWest()],[bb.getSouth(),bb.getWest()],[bb.getSouth(),bb.getEast()],[bb.getNorth(),bb.getEast()]];\nvar mask=L.polygon([world,shapePts],{pane:\'mask\',renderer:svgRenderer,stroke:false,fillColor:css(\'--bg\'),fillOpacity:1,fillRule:\'evenodd\',interactive:false}).addTo(map);\nvar outline=L.polygon(shapePts,{pane:\'edge\',renderer:renderer,color:css(\'--edge\'),weight:1,opacity:1,fill:false,interactive:false}).addTo(map);\nvar tileLayer=L.tileLayer(\'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}\',{pane:\'tiles\',maxZoom:19,detectRetina:true,opacity:.6});\nvar tilesOn=false;\nfunction popup(f,l){if(f.properties&&f.properties.i)l.bindPopup(f.properties.i,{maxWidth:300});}\nfunction polygons(features,color,opacity,weight){return L.geoJSON({type:\'FeatureCollection\',features:features},{pane:\'data\',renderer:renderer,onEachFeature:popup,style:function(){return{color:css(color),weight:weight,fillColor:css(color),fillOpacity:opacity};}});}\nvar layers={},shown={gaps:true,gaps3d:false,gaptrees:false,buildings3d:false,buildings2d:false,trees:false,labels:true};\nlayers.gaps=polygons(data.gaps,\'--gap\',.5,.7);\nlayers.gaps3d=polygons(data.gaps3d,\'--gap3\',.42,.7);\nlayers.gaptrees=polygons(data.gaptrees,\'--gapT\',.35,.6);\nlayers.buildings3d=polygons(data.buildings3d,\'--b3\',.82,.3);\nlayers.buildings2d=polygons(data.buildings2d,\'--b2\',.8,.3);\nlayers.trees=L.layerGroup();\ndata.trees.forEach(function(p){L.circleMarker([p[0],p[1]],{pane:\'data\',renderer:renderer,radius:2.2,color:css(\'--tree\'),weight:.6,fillColor:css(\'--tree\'),fillOpacity:.9}).addTo(layers.trees);});\nvar gapBadges=L.layerGroup(),gapDots=L.layerGroup();\nfunction cellName(props){\n  var byPoint=props&&props.b;if(byPoint)return byPoint;\n  var inner=(props&&props.i||\'\'),m=inner.match(/<b>([^<]*)<\\/b>/);if(m)return m[1];\n  return null;\n}\nfunction nearestLabel(lat,lon){\n  var best=null,bd=Infinity,c=Math.cos(lat*Math.PI/180);\n  data.labels.forEach(function(o){var d=Math.hypot(lat-o.lat,(lon-o.lon)*c);if(d<bd){bd=d;best=o;}});\n  return best;\n}\nfunction cellCenter(geom){\n  var c=geom.coordinates,r=geom.type===\'Polygon\'?c[0]:(c[0]||[[]])[0];\n  if(!r.length)return null;\n  var lat=0,lon=0;r.forEach(function(p){lon+=p[0];lat+=p[1];});\n  return[lat/r.length,lon/r.length];\n}\n(function buildSummary(){\n  var byGroup={};\n  function add(features){\n    features.forEach(function(f){\n      var center=cellCenter(f.geometry);if(!center)return;\n      var props=f.properties||{},name=cellName(props);\n      if(!name){var lab=nearestLabel(center[0],center[1]);name=lab?lab.n:\'Mairena\';}\n      var g=byGroup[name]||(byGroup[name]={n:0,lat:0,lon:0});\n      g.n++;g.lat+=center[0];g.lon+=center[1];\n    });\n  }\n  add(data.gaps);\n  Object.keys(byGroup).forEach(function(name){\n    var g=byGroup[name],lat=g.lat/g.n,lon=g.lon/g.n;\n    gapDots.addLayer(L.circleMarker([lat,lon],{pane:\'data\',renderer:renderer,radius:4,color:css(\'--gap\'),weight:1.2,fillColor:css(\'--gap\'),fillOpacity:.9,interactive:true})\n      .bindPopup(\'<b>\'+escapeHtml(name)+\'</b><br>\'+g.n+\' celdas con huecos de edificios\',{maxWidth:240}));\n    gapBadges.addLayer(L.marker([lat,lon],{interactive:false,keyboard:false,icon:L.divIcon({className:\'\',iconSize:[44,24],iconAnchor:[22,12],html:\'<div class="gap-badge">\'+g.n+\'</div>\'})}));\n  });\n})();\nfunction labelsFor(zoom){\n  var max=zoom<12?5:zoom<13?10:zoom<15?22:1000,\n      dist=zoom<12?.010:zoom<13?.007:zoom<15?.0035:.0012,\n      accepted=[];\n  data.labels.slice().sort(function(a,b){return b.area-a.area;}).forEach(function(item){\n    if(accepted.length>=max)return;\n    var c=Math.cos(item.lat*Math.PI/180);\n    if(accepted.some(function(o){return Math.hypot(item.lat-o.lat,(item.lon-o.lon)*c)<dist;}))return;\n    accepted.push(item);\n  });\n  return accepted;\n}\nvar labelMarkers={};\ndata.labels.forEach(function(item){\n  var marker=L.marker([item.lat,item.lon],{interactive:false,keyboard:false,icon:L.divIcon({className:\'\',iconSize:[160,24],iconAnchor:[80,12],html:\'<div class="neighbour-label">\'+escapeHtml(item.n)+\'</div>\'})});\n  labelMarkers[item.n]=marker;\n});\nlayers.labels=L.layerGroup();\nfunction updateLabels(){\n  layers.labels.clearLayers();\n  if(!shown.labels)return;\n  labelsFor(map.getZoom()).forEach(function(item){var m=labelMarkers[item.n];if(m)layers.labels.addLayer(m);});\n  if(!map.hasLayer(layers.labels))layers.labels.addTo(map);\n}\nfunction on(key){var want={gaps:shown.gaps,labels:shown.labels,gaps3d:shown.gaps3d,gaptrees:shown.gaptrees};\n  if(want[key]!==undefined)return want[key];\n  return shown[key]&&map.getZoom()>=DETAIL;}\nfunction sync(){\n  var zoom=map.getZoom(),low=zoom<DETAIL;\n  document.getElementById(\'zoomReadout\').textContent=low?\'vista completa\':\'zoom \'+zoom.toFixed(1);\n  root.style.setProperty(\'--zoom\',zoom);\n  [[\'gaps\',on(\'gaps\')],[\'gaps3d\',on(\'gaps3d\')],[\'gaptrees\',on(\'gaptrees\')],[\'buildings3d\',on(\'buildings3d\')],\n   [\'buildings2d\',on(\'buildings2d\')],[\'trees\',on(\'trees\')]].forEach(function(pair){\n    var key=pair[0],want=pair[1],has=map.hasLayer(layers[key]);\n    if(want&&!has){map.addLayer(layers[key]);layers[key].bringToFront();}\n    else if(!want&&has)map.removeLayer(layers[key]);\n  });\n  if(shown.gaps&&low){if(!map.hasLayer(gapBadges))gapBadges.addTo(map);if(!map.hasLayer(gapDots))gapDots.addTo(map);}\n  else{map.removeLayer(gapBadges);map.removeLayer(gapDots);}\n  updateLabels();\n}\nfunction showLayer(key,value){\n  shown[key]=value;\n  if(key===\'labels\')updateLabels();\n  sync();\n}\nwindow.refreshMapTheme=function(){\n  mask.setStyle({fillColor:css(\'--bg\')});\n  outline.setStyle({color:css(\'--edge\')});\n  [\'gaps\',\'gaps3d\',\'gaptrees\',\'buildings3d\',\'buildings2d\'].forEach(function(k){\n    var palette={gaps:[\'--gap\',.5,.7],gaps3d:[\'--gap3\',.42,.7],gaptrees:[\'--gapT\',.35,.6],buildings3d:[\'--b3\',.82,.3],buildings2d:[\'--b2\',.8,.3]}[k];\n    layers[k].setStyle({color:css(palette[0]),fillColor:css(palette[0]),weight:palette[2],fillOpacity:palette[1]});\n  });\n  layers.trees.eachLayer(function(m){m.setStyle({color:css(\'--tree\'),fillColor:css(\'--tree\')});});\n  gapDots.eachLayer(function(m){m.setStyle({color:css(\'--gap\'),fillColor:css(\'--gap\')});});\n  sync();\n};\nArray.prototype.forEach.call(document.querySelectorAll(\'[data-layer]\'),function(box){\n  box.addEventListener(\'change\',function(){showLayer(box.dataset.layer,box.checked);});\n});\ndocument.getElementById(\'streets\').addEventListener(\'change\',function(e){\n  tilesOn=e.target.checked;\n  if(tilesOn){tileLayer.addTo(map);}else{map.removeLayer(tileLayer);}\n  sync();\n});\ndocument.getElementById(\'print\').addEventListener(\'click\',function(){window.print();});\ndocument.getElementById(\'home\').addEventListener(\'click\',function(){fitShape();});\nfunction fitShape(){\n  map.fitBounds(bounds,{paddingTopLeft:[24,72],paddingBottomRight:[24,24]});\n  var fit=map.getBounds();if(map.getZoom()<fitZoom())map.setZoom(fitZoom(),{animate:false});\n}\nfunction fitZoom(){\n  map.invalidateSize();\n  var size=map.getSize(),view=limit;\n  var nw=map.project(view.getNorthWest(),0),se=map.project(view.getSouthEast(),0);\n  var scale=Math.min(size.x/(se.x-nw.x),size.y/(se.y-nw.y));\n  return Math.log(scale)/Math.LN2;\n}\nfunction applyMinZoom(){\n  var z=fitZoom(),snapped=map.options.zoomSnap>0?Math.floor(z/map.options.zoomSnap)*map.options.zoomSnap:z;\n  map.setMinZoom(snapped);\n  if(map.getZoom()<snapped)map.setZoom(snapped,{animate:false});\n}\nvar pendingFit=true;\nfunction boot(){\n  pendingFit=false;\n  applyMinZoom();\n  var fitZ=fitZoom();\n  map.setView(bounds.getCenter(),Math.max(map.getMinZoom(),map.options.zoomSnap>0?Math.floor(fitZ/map.options.zoomSnap)*map.options.zoomSnap:fitZ),{animate:false});\n  var view=map.getBounds();\n  if(!view.contains(bounds))fitShape();\n  sync();\n}\nmap.on(\'zoomend moveend resize\',function(){if(pendingFit)return;if(map.getZoom()<map.getMinZoom())applyMinZoom();sync();});\nif(tilesOn)tileLayer.addTo(map);\nboot();\nshowLayer(\'gaps\',true);\nshowLayer(\'labels\',true);\nmap.once(\'moveend\',function(){pendingFit=false;applyMinZoom();sync();});\n})();\n</script></body></html>'


def leaflet_asset(name):
    last_error = None
    for url in LEAFLET_URLS[name]:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; MairenaOSMHuecos/3.0)"})
            with urllib.request.urlopen(request, timeout=60) as response:
                text = response.read().decode("utf-8")
                if text:
                    return text
        except Exception as error:
            last_error = error
            print("  aviso: no se pudo descargar " + url + " (" + str(error) + ")")
    raise RuntimeError("No se pudo descargar " + name + ": " + str(last_error))


def cached_leaflet_asset(name):
    cache_dir = os.path.join(os.path.dirname(__file__), ".leaflet-cache")
    path = os.path.join(cache_dir, name)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as cache:
            content = cache.read()
        if content:
            print("   Leaflet " + name + ": desde cache local (" + str(len(content)) + " bytes)")
            return content
    content = leaflet_asset(name)
    os.makedirs(cache_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as cache:
        cache.write(content)
    print("   Leaflet " + name + ": descargado y guardado (" + str(len(content)) + " bytes)")
    return content


def overpass(query):
    headers = {"User-Agent": OVERPASS_UA, "Accept": "*/*"}
    last_error = None
    for attempt in range(3):
        for url in OVERPASS:
            for method in ("POST", "GET"):
                try:
                    if method == "POST":
                        response = requests.post(url, data={"data": query}, headers=headers, timeout=90)
                    else:
                        response = requests.get(url, params={"data": query}, headers=headers, timeout=90)
                    if response.status_code == 200:
                        return response.json()
                    print("  " + method + " " + url + " devolvio " + str(response.status_code))
                    last_error = "HTTP " + str(response.status_code)
                    if response.status_code in (400, 406):
                        continue
                    break
                except requests.RequestException as error:
                    last_error = error
                    print("  " + method + " " + url + " error de red: " + str(error)[:90])
        if attempt < 2:
            wait = 10 + attempt * 10
            print("  esperando " + str(wait) + "s antes de reintentar...")
            time.sleep(wait)
    sys.exit("No se pudo consultar Overpass (" + str(last_error) + "). Prueba de nuevo en unos minutos.")


def relation_geometry(element):
    lines = []
    for member in element.get("members", []):
        if member.get("role") == "outer" and member.get("geometry"):
            points = [(p["lon"], p["lat"]) for p in member["geometry"]]
            if len(points) >= 2:
                lines.append(LineString(points))
    polygons = list(polygonize(linemerge(lines))) if lines else []
    return unary_union(polygons) if polygons else None


def element_geometry(element):
    if element.get("type") == "relation":
        return relation_geometry(element)
    coords = element.get("geometry")
    if not coords or len(coords) < 4:
        return None
    geom = Polygon([(p["lon"], p["lat"]) for p in coords])
    if not geom.is_valid:
        geom = geom.buffer(0)
    return geom if not geom.is_empty else None


def has_3d(tags):
    return any(key in tags for key in ("height", "building:levels", "building:height"))


def nearest_neighbourhood(lat, lon, neighbourhoods, coslat):
    if not neighbourhoods:
        return "(sin barrio)"
    return min(neighbourhoods, key=lambda b: (lat - b["lat"]) ** 2 + ((lon - b["lon"]) * coslat) ** 2)["name"]


def rounded_coordinates(value):
    if isinstance(value, (tuple, list)):
        if len(value) >= 2 and isinstance(value[0], (int, float)) and isinstance(value[1], (int, float)):
            return [round(value[0], 6), round(value[1], 6)]
        return [rounded_coordinates(item) for item in value]
    return value


def geometry_json(geom):
    simple = geom.simplify(0.5 / 111320.0, preserve_topology=True)
    result = mapping(simple)
    result["coordinates"] = rounded_coordinates(result["coordinates"])
    return result


def feature(geom, properties=None):
    return {"type": "Feature", "geometry": geometry_json(geom), "properties": properties or {}}


def generate_html(boundary, gaps, gaps3d, gaptrees, trees, buildings3d, buildings2d, neighbourhoods, leaflet_js, leaflet_css):
    labels = []
    for item in neighbourhoods:
        point = Point(item["lon"], item["lat"])
        if not boundary.covers(point):
            point = boundary.representative_point()
            item["lat"], item["lon"] = point.y, point.x
        name = re.sub(r"^Urbanizacion\s+", "", item["name"], flags=re.IGNORECASE).strip()
        labels.append({"n": name, "lat": round(item["lat"], 6), "lon": round(item["lon"], 6), "area": item.get("area", 1)})
    data = {"boundary": geometry_json(boundary), "gaps": gaps, "gaps3d": gaps3d, "gaptrees": gaptrees,
            "trees": [[round(lat, 6), round(lon, 6)] for lat, lon in trees if boundary.covers(Point(lon, lat))],
            "buildings3d": buildings3d, "buildings2d": buildings2d, "labels": labels}
    data_json = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    logo_data = ""
    logo_path = os.path.join(os.path.dirname(__file__), "_logo_clean.svg")
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as logo_file:
            logo_data = "data:image/svg+xml;base64," + base64.b64encode(logo_file.read()).decode("ascii")
    leaflet_css = re.sub(r"url\([^)]*\)", "none", leaflet_css)
    page = LEAFLET_TEMPLATE
    page = page.replace("@@LEAFLET_CSS@@", leaflet_css).replace("@@LEAFLET_JS@@", leaflet_js).replace("@@LOGO@@", logo_data).replace("@@DATA@@", data_json)
    with open(SALIDA_HTML, "w", encoding="utf-8", newline="\n") as output:
        output.write(page)


def main():
    if os.path.exists(DATOS_JSON):
        main_desde_json()
    else:
        main_desde_overpass()


def main_desde_json():
    print("Cargando datos locales desde " + os.path.basename(DATOS_JSON) + " (sin Overpass)...")
    with open(DATOS_JSON, "r", encoding="utf-8") as handle:
        datos = json.load(handle)
    boundary = shape(datos["boundary"])
    if not boundary.is_valid:
        boundary = boundary.buffer(0)
    print("   limites: " + str([round(v, 4) for v in boundary.bounds]))
    neighbourhood_list = []
    priority = {"town": 4, "quarter": 3, "suburb": 2, "neighbourhood": 1}
    for item in datos.get("neighbourhoods", []):
        point = Point(item["lon"], item["lat"])
        if boundary.covers(point):
            neighbourhood_list.append({
                "name": item["name"], "lat": item["lat"], "lon": item["lon"],
                "area": priority.get(item.get("place"), 1) * 1000000,
            })
    print("   " + str(len(neighbourhood_list)) + " nombres de barrio")
    residential = [shape(g) for g in datos.get("residential", [])]
    residential_union = unary_union(residential) if residential else boundary
    coslat = math.cos(math.radians((boundary.bounds[1] + boundary.bounds[3]) / 2))
    buildings3d, buildings2d = [], []
    cell_stats, neighbourhood_stats = {}, {}
    meters_per_degree_sq = (111320.0 ** 2) * coslat
    minx, miny, maxx, maxy = boundary.bounds
    dy = CELDA_M / 111320.0
    dx = dy / coslat

    def cell_key(lat, lon):
        return int((lon - minx) / dx), int((lat - miny) / dy)

    lista_3d = datos.get("buildings3d", [])
    lista_2d = datos.get("buildings2d", [])
    for f in lista_3d:
        f.setdefault("properties", {})["_3d"] = True
    for f in lista_2d:
        f.setdefault("properties", {})["_3d"] = False
    for f in lista_3d + lista_2d:
        is_3d = f.get("properties", {}).pop("_3d", False)
        geom = shape(f["geometry"])
        if geom.is_empty or geom.area == 0:
            continue
        center = geom.centroid
        stat = cell_stats.setdefault(cell_key(center.y, center.x), {"area": 0.0, "n": 0, "n3": 0, "trees": 0})
        stat["area"] += geom.area * meters_per_degree_sq
        stat["n"] += 1
        name = nearest_neighbourhood(center.y, center.x, neighbourhood_list, coslat)
        nstat = neighbourhood_stats.setdefault(name, {"buildings": 0, "3d": 0, "2d": 0, "trees": 0, "gaps": 0, "gaps3d": 0, "gaptrees": 0})
        nstat["buildings"] += 1
        if is_3d:
            stat["n3"] += 1
            nstat["3d"] += 1
        else:
            nstat["2d"] += 1
        (buildings3d if is_3d else buildings2d).append(f)
    print("   " + str(len(buildings3d) + len(buildings2d)) + " edificios")
    trees = []
    for lat, lon in datos.get("trees", []):
        if boundary.covers(Point(lon, lat)):
            trees.append((lat, lon))
            cell_stats.setdefault(cell_key(lat, lon), {"area": 0.0, "n": 0, "n3": 0, "trees": 0})["trees"] += 1
            neighbourhood_stats.setdefault(nearest_neighbourhood(lat, lon, neighbourhood_list, coslat), {"buildings": 0, "3d": 0, "2d": 0, "trees": 0, "gaps": 0, "gaps3d": 0, "gaptrees": 0})["trees"] += 1
    print("   " + str(len(trees)) + " arboles")
    print("Calculando huecos por celda...")
    gaps, gaps3d, gaptrees = [], [], []
    nx, ny = int(math.ceil((maxx - minx) / dx)), int(math.ceil((maxy - miny) / dy))
    for i in range(nx):
        for j in range(ny):
            cell = box(minx + i * dx, miny + j * dy, minx + (i + 1) * dx, miny + (j + 1) * dy).intersection(boundary)
            if cell.is_empty or cell.area < 0.2 * dx * dy:
                continue
            urban = cell.intersection(residential_union)
            if urban.area / cell.area < MIN_URBANO:
                continue
            stat = cell_stats.get((i, j), {"area": 0.0, "n": 0, "n3": 0, "trees": 0})
            urban_area = urban.area * meters_per_degree_sq
            coverage = stat["area"] / urban_area if urban_area else 0
            tree_rate = stat["trees"] / (urban_area / 10000.0) if urban_area else 0
            center = cell.representative_point()
            name = nearest_neighbourhood(center.y, center.x, neighbourhood_list, coslat)
            nstat = neighbourhood_stats.setdefault(name, {"buildings": 0, "3d": 0, "2d": 0, "trees": 0, "gaps": 0, "gaps3d": 0, "gaptrees": 0})
            info = ("<b>" + html.escape(name) + "</b><br>Edificios: " + str(stat["n"]) + " (con altura: " + str(stat["n3"]) + ")<br>"
                    + "Cobertura: " + format(coverage, ".0%") + "<br>Arboles: " + str(stat["trees"]) + " (" + format(tree_rate, ".1f") + "/ha)<br>"
                    + '<a href="https://www.openstreetmap.org/edit?editor=id#map=18/' + format(center.y, ".6f") + "/" + format(center.x, ".6f") + '">Editar en iD</a>')
            item = feature(cell, {"i": info, "b": name})
            if coverage < MIN_COBERTURA_EDIF:
                gaps.append(item)
                nstat["gaps"] += 1
            elif stat["n"] and stat["n3"] / stat["n"] < MIN_RATIO_3D:
                gaps3d.append(item)
                nstat["gaps3d"] += 1
            if tree_rate < MIN_ARBOLES_HA:
                gaptrees.append(item)
                nstat["gaptrees"] += 1
    print("   " + str(len(gaps)) + " huecos de edificios, " + str(len(gaps3d)) + " de altura, " + str(len(gaptrees)) + " de arboles")
    print("Generando HTML autonomo...")
    generate_html(boundary, gaps, gaps3d, gaptrees, trees, buildings3d, buildings2d, neighbourhood_list, cached_leaflet_asset("leaflet.js"), cached_leaflet_asset("leaflet.css"))
    with open(SALIDA_CSV, "w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["barrio", "edificios", "con_3D", "sin_3D", "pct_3D", "arboles", "celdas_sin_edificios", "celdas_sin_3D", "celdas_faltan_arboles"])
        for name in sorted(neighbourhood_stats):
            stat = neighbourhood_stats[name]
            pct = stat["3d"] / stat["buildings"] if stat["buildings"] else 0
            writer.writerow([name, stat["buildings"], stat["3d"], stat["2d"], format(pct, ".0%"), stat["trees"], stat["gaps"], stat["gaps3d"], stat["gaptrees"]])
    print("Listo: " + SALIDA_HTML + " y " + SALIDA_CSV)


def main_desde_overpass():
    if os.path.exists(POLY_FILE):
        print("1/6 Cargando limite municipal desde " + os.path.basename(POLY_FILE) + "...")
        boundary = poligono_desde_polyfile(POLY_FILE, SECCION_POLY)
    else:
        print("1/6 Descargando limite municipal de Overpass...")
        q = ('[out:json][timeout:120];rel["boundary"="administrative"]'
             '["admin_level"="8"]["name"="' + MUNICIPIO + '"];out geom;')
        result = overpass(q)
        if not result["elements"]:
            result = overpass('[out:json][timeout:120];rel["boundary"="administrative"]'
                              '["name"="' + MUNICIPIO + '"];out geom;')
        boundary = None
        for element in result["elements"]:
            boundary = relation_geometry(element)
            if boundary is not None:
                break
        if boundary is None:
            sys.exit("No encontre el limite del municipio en OSM.")
    print("   limites: " + str([round(v, 4) for v in boundary.bounds]))
    print("2/6 Descargando barrios y suelo residencial...")
    result = overpass('[out:json][timeout:240];' + AREA + '(nwr["place"~"^(suburb|neighbourhood|quarter)$"](area.a);out center tags;')
    neighbourhoods = {}
    priority = {"suburb": 3, "quarter": 2, "neighbourhood": 1}
    for element in result["elements"]:
        tags = element.get("tags", {})
        name = tags.get("name")
        center = element.get("center", {})
        lat = element.get("lat", center.get("lat"))
        lon = element.get("lon", center.get("lon"))
        if name and lat is not None and lon is not None:
            neighbourhoods[name] = {"name": name, "lat": lat, "lon": lon, "area": priority.get(tags.get("place"), 1) * 1000000}
    result = overpass('[out:json][timeout:240];' + AREA + '(way["landuse"="residential"](area.a);rel["landuse"="residential"](area.a);out tags geom;')
    residential = []
    for element in result["elements"]:
        geom = element_geometry(element)
        if geom is None:
            continue
        geom = geom.intersection(boundary)
        if not geom.is_empty:
            residential.append(geom)
        name = element.get("tags", {}).get("name")
        if name and name not in neighbourhoods:
            point = geom.representative_point()
            neighbourhoods[name] = {"name": name, "lat": point.y, "lon": point.x, "area": max(1, int(geom.area * 1e12))}
    residential_union = unary_union(residential) if residential else boundary
    neighbourhood_list = [n for n in neighbourhoods.values() if boundary.covers(Point(n["lon"], n["lat"]))]
    coslat = math.cos(math.radians((boundary.bounds[1] + boundary.bounds[3]) / 2))
    print("   " + str(len(neighbourhood_list)) + " nombres de barrio")
    print("3/6 Descargando edificios...")
    result = overpass('[out:json][timeout:300];' + AREA + '(way["building"](area.a);way["building:part"](area.a);out tags geom;')
    buildings3d, buildings2d = [], []
    cell_stats, neighbourhood_stats = {}, {}
    meters_per_degree_sq = (111320.0 ** 2) * coslat
    minx, miny, maxx, maxy = boundary.bounds
    dy = CELDA_M / 111320.0
    dx = dy / coslat
    def cell_key(lat, lon):
        return int((lon - minx) / dx), int((lat - miny) / dy)
    for element in result["elements"]:
        geom = element_geometry(element)
        if geom is None:
            continue
        geom = geom.intersection(boundary)
        if geom.is_empty or geom.area == 0:
            continue
        geom = geom.simplify(0.5 / 111320.0, preserve_topology=True)
        center = geom.centroid
        stat = cell_stats.setdefault(cell_key(center.y, center.x), {"area": 0.0, "n": 0, "n3": 0, "trees": 0})
        stat["area"] += geom.area * meters_per_degree_sq
        stat["n"] += 1
        name = nearest_neighbourhood(center.y, center.x, neighbourhood_list, coslat)
        nstat = neighbourhood_stats.setdefault(name, {"buildings": 0, "3d": 0, "2d": 0, "trees": 0, "gaps": 0, "gaps3d": 0, "gaptrees": 0})
        nstat["buildings"] += 1
        is_3d = has_3d(element.get("tags", {}))
        if is_3d:
            stat["n3"] += 1
            nstat["3d"] += 1
        else:
            nstat["2d"] += 1
        (buildings3d if is_3d else buildings2d).append(feature(geom))
    print("   " + str(len(buildings3d) + len(buildings2d)) + " edificios")
    print("4/6 Descargando arboles...")
    result = overpass('[out:json][timeout:240];' + AREA + '(node["natural"="tree"](area.a);out;')
    trees = [(e["lat"], e["lon"]) for e in result["elements"] if boundary.covers(Point(e["lon"], e["lat"]))]
    for lat, lon in trees:
        cell_stats.setdefault(cell_key(lat, lon), {"area": 0.0, "n": 0, "n3": 0, "trees": 0})["trees"] += 1
        neighbourhood_stats.setdefault(nearest_neighbourhood(lat, lon, neighbourhood_list, coslat), {"buildings": 0, "3d": 0, "2d": 0, "trees": 0, "gaps": 0, "gaps3d": 0, "gaptrees": 0})["trees"] += 1
    print("   " + str(len(trees)) + " arboles")
    print("5/6 Calculando huecos por celda...")
    gaps, gaps3d, gaptrees = [], [], []
    nx, ny = int(math.ceil((maxx - minx) / dx)), int(math.ceil((maxy - miny) / dy))
    for i in range(nx):
        for j in range(ny):
            cell = box(minx + i * dx, miny + j * dy, minx + (i + 1) * dx, miny + (j + 1) * dy).intersection(boundary)
            if cell.is_empty or cell.area < 0.2 * dx * dy:
                continue
            urban = cell.intersection(residential_union)
            if urban.area / cell.area < MIN_URBANO:
                continue
            stat = cell_stats.get((i, j), {"area": 0.0, "n": 0, "n3": 0, "trees": 0})
            urban_area = urban.area * meters_per_degree_sq
            coverage = stat["area"] / urban_area if urban_area else 0
            tree_rate = stat["trees"] / (urban_area / 10000.0) if urban_area else 0
            center = cell.representative_point()
            name = nearest_neighbourhood(center.y, center.x, neighbourhood_list, coslat)
            nstat = neighbourhood_stats.setdefault(name, {"buildings": 0, "3d": 0, "2d": 0, "trees": 0, "gaps": 0, "gaps3d": 0, "gaptrees": 0})
            info = ("<b>" + html.escape(name) + "</b><br>Edificios: " + str(stat["n"]) + " (con altura: " + str(stat["n3"]) + ")<br>"
                    + "Cobertura: " + format(coverage, ".0%") + "<br>Arboles: " + str(stat["trees"]) + " (" + format(tree_rate, ".1f") + "/ha)<br>"
                    + '<a href="https://www.openstreetmap.org/edit?editor=id#map=18/' + format(center.y, ".6f") + "/" + format(center.x, ".6f") + '">Editar en iD</a>')
            item = feature(cell, {"i": info, "b": name})
            if coverage < MIN_COBERTURA_EDIF:
                gaps.append(item)
                nstat["gaps"] += 1
            elif stat["n"] and stat["n3"] / stat["n"] < MIN_RATIO_3D:
                gaps3d.append(item)
                nstat["gaps3d"] += 1
            if tree_rate < MIN_ARBOLES_HA:
                gaptrees.append(item)
                nstat["gaptrees"] += 1
    print("   " + str(len(gaps)) + " huecos de edificios, " + str(len(gaps3d)) + " de altura, " + str(len(gaptrees)) + " de arboles")
    print("6/6 Generando HTML autonomo...")
    generate_html(boundary, gaps, gaps3d, gaptrees, trees, buildings3d, buildings2d, neighbourhood_list, cached_leaflet_asset("leaflet.js"), cached_leaflet_asset("leaflet.css"))
    with open(SALIDA_CSV, "w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["barrio", "edificios", "con_3D", "sin_3D", "pct_3D", "arboles", "celdas_sin_edificios", "celdas_sin_3D", "celdas_faltan_arboles"])
        for name in sorted(neighbourhood_stats):
            stat = neighbourhood_stats[name]
            pct = stat["3d"] / stat["buildings"] if stat["buildings"] else 0
            writer.writerow([name, stat["buildings"], stat["3d"], stat["2d"], format(pct, ".0%"), stat["trees"], stat["gaps"], stat["gaps3d"], stat["gaptrees"]])
    print("Listo: " + SALIDA_HTML + " y " + SALIDA_CSV)


if __name__ == "__main__":
    main()
