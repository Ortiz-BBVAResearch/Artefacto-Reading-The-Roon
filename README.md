# Monitor Macro España

Dashboard estático (GitHub Pages) con los principales indicadores macroeconómicos de España a partir de fuentes oficiales: **INE**, **Banco de España** y **Ministerio de Economía, Comercio y Empresa (BDSICE)**. Misma arquitectura que *Reading the Room with AI*: `index.html` + `data.json`, un script Python que refresca los datos y una GitHub Action programada.

## Contenido
| Fichero | Qué hace |
|---|---|
| `update_data.py` | Descarga 72 series (API Tempus3 del INE, CSV del BdE, tablas PX de afiliados de la Seguridad Social, ficheros de paro registrado del SEPE y ZIP completo de BDSICE) y escribe `data.json`. Si una fuente falla, conserva los datos anteriores de esa serie. Catálogo al principio del script (`CAT`). |
| `build_page.py` | Incrusta `data.json` en `template.html` → `index.html` (documento completo, funciona también offline) y `artifact.html` (versión para claude.ai). |
| `i18n.js` | Traducciones al inglés (clave = texto en español). `build_page.py` lo incrusta en la página; el selector ES / EN de la cabecera cambia el idioma y se recuerda en el navegador. También se puede abrir directamente en inglés con `?lang=en`. |
| `forecasts.json` | Previsiones de BBVA Research (Spain Economic Outlook). Se edita a mano con cada nuevo informe. |
| `template.html` | Página: pestañas Resumen, Explorador, Actividad, Empleo, Precios, Sector público y exterior, Financiero, Vivienda, Previsiones, Tablas, Fuentes y método. Gráficos SVG propios, sin librerías. |
| `.github/workflows/update-data.yml` | Ejecuta los dos scripts los días laborables (09:17 y 16:17 Madrid en invierno) y con *Run workflow* manual; hace commit si cambian los datos. |
| `update_log.md` | Registro de cada actualización y errores de descarga. |

## Puesta en marcha
1. Crear el repositorio y subir el contenido de esta carpeta.
2. *Settings → Pages*: desplegar desde la rama `main`, carpeta raíz.
3. *Settings → Actions → General → Workflow permissions*: **Read and write**.
4. *Actions → Update data → Run workflow* para la primera actualización.

En local: `pip install requests && python update_data.py data.json && python build_page.py && python -m http.server 8000`.

## Botón «Actualizar datos»
Relee `data.json` del propio sitio (y lo hace solo cada 15 minutos). Los datos nuevos llegan cuando la Action los publica; para forzarlo, lanzar la Action a mano.

## Añadir una serie
Añadir una línea a `CAT` en `update_data.py` con `(id, fuente, código, etiqueta, unidad, frecuencia, bloque, extra)`:
- INE: código de serie Tempus (p. ej. `IPC290750`), buscar en `servicios.ine.es/wstempus/js/ES/SERIES_TABLA/<tabla>`.
- Banco de España: `bde:<tabla>` y el código de serie de la primera fila del CSV (p. ej. `bde:be1904`, `DN_1TI2T0002`).
- BDSICE: nombre del fichero dentro de `BdsiceCSV.zip` sin `.csv` (p. ej. `190000m.d`).
- `{"transform": "yoy"}` calcula la tasa interanual desde niveles.
Después, añadirla a un gráfico en `FIGS` o a una tabla en `template.html`.

## Notas de método
- Afiliación (Seguridad Social, afiliados medios: tablas 10m y 10mb, desestacionalizada) y paro registrado (SEPE, datos originales) se toman de la fuente primaria y se actualizan el mismo día de su publicación.
- Sin estimaciones: solo tasas interanuales, sumas móviles (4T / 12M) y cocientes sobre PIB nominal.
- El saldo trimestral de la IGAE viene acumulado en el año; se desacumula antes de sumar 4 trimestres.
- Cuenta corriente en % del PIB: suma de 12 meses sobre el PIB nominal de los últimos 4 trimestres disponibles.
- Prima de riesgo: diferencia diaria bono 10 años España − Alemania (BdE vía BDSICE).
- Crédito y depósitos: variación interanual del saldo vivo (no corrige saneamientos ni reclasificaciones).
- Los datos de avance del INE (IPC adelantado) se marcan como «avance».
