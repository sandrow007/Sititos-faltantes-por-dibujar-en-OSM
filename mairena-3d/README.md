# Mairena del Aljarafe · modelo 3D

Paquete autocontenido para añadir el visor 3D al repositorio sin instalar dependencias.

## Contenido

- `Mairena_Elefante_Real.glb` — geometría principal: Catastro, OSM, parques, calles, árboles y alcorques. Comprimido con Draco (49 MB → 2,5 MB); la base sólida y el terreno van ocultos por defecto para no tapar el modelo (interruptor en el HUD).
- `Mairena_Etiquetas.glb` — capa opcional de nombres de barrios y calles.
- `index.html` — visor local con controles orbitales.
- `vendor/` — Three.js, GLTFLoader, DRACOLoader (con decodificador en `vendor/draco/`), OrbitControls y three-mesh-bvh (raycast rápido).

## Interacción

- Arrastrar: girar · rueda: zoom · clic derecho o Mayús+arrastrar: paneo · táctil: un dedo gira, dos hacen zoom/paneo.
- Clic en un edificio: vuelo suave de acercamiento; doble clic: vuelta a la vista general.
- Al pasar el ratón se resalta el elemento y se muestra su categoría (Catastro/OSM/árbol/alcorque…).
- El terreno/base sólido y las etiquetas son opcionales desde el HUD (`Mostrar terreno y base`, `Mostrar nombres`).
- Render bajo demanda: solo se dibuja cuando la cámara se mueve, con resolución adaptativa si los fps bajan.

## Añadirlo al repositorio

1. Descomprime la carpeta en la raíz del repositorio.
2. Ábrelo desde un servidor local (`python -m http.server`) — las texturas WASM de Draco no cargan con `file://` en algunos navegadores.
3. Para enlazarlo desde tu mapa, añade un botón a `./mairena-3d/index.html`.

## Nota de altura

El repositorio identifica los edificios OSM con altura documentada, pero no conserva su valor numérico. En el modelo, el violeta oscuro marca esa categoría; las demás extrusiones son ilustrativas. Las huellas y posiciones proceden de los datos reales del repositorio.

Licencia del código base del repositorio: AGPL-3.0. Three.js y three-mesh-bvh se distribuyen bajo MIT y se incluyen junto a sus avisos de licencia.
