# Mi Propio IPC — Región Noroeste (Santiago del Estero)

Calculadora de inflación personal: cargás cuánto gastaste este mes en cada
rubro y calcula tu variación de precios personal, comparada con el IPC
oficial de la región Noroeste (NOA) y con el IPC Nacional.

## Cómo correrla

```bash
pip install -r requirements.txt
streamlit run app.py
```

No necesita internet: usa los archivos ya incluidos en `data/`:

- `serie_ipc_divisiones.csv` — Nivel general del IPC por región (INDEC).
- `sh_ipc_aperturas.xls` — Variación mensual por apertura y región (INDEC),
  hoja "Variación mensual aperturas".

## Estructura

```
app.py         -> interfaz Streamlit
data_ipc.py    -> parsers de los 2 archivos + motor de cálculo
data/          -> los 2 archivos oficiales del INDEC
requirements.txt
```

## Actualizar los datos más adelante

Para refrescar `data/` con una versión más nueva, alcanza con reemplazar
esos dos archivos por los que se descarguen de:

- https://www.indec.gob.ar/ftp/cuadros/economia/serie_ipc_divisiones.csv
- https://www.indec.gob.ar/ftp/cuadros/economia/sh_ipc_aperturas.xls

`data_ipc.py` no depende de nombres de columna fijos por posición: detecta
los bloques por región y hace matching por similitud de texto para cada
apertura, así que tolera pequeños cambios de formato de un mes a otro. Si
el INDEC cambia la estructura de fondo, `datos.aperturas_sin_match()`
va a devolver qué rubros dejaron de encontrarse (también se muestra como
aviso en la barra lateral de la app).
