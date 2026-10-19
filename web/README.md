# Web de FOOTDATA

## Equipos y posiciones

La vista Líderes destaca catorce categorías: mejor ataque y defensa, más remates y tiros al arco, más córners, menos remates/tiros/córners concedidos, cantidades máximas y mínimas de tarjetas y faltas propias, tarjetas del rival y faltas recibidas. Cada tarjeta indica el criterio y la muestra; más tarjetas no se presenta como mejor rendimiento. Los líderes comparan toda la competición, muestran los empates y se pueden filtrar por localía y por promedio o total. Las tablas completas conservan su vista Estadísticas y su buscador. Acceso directo de ejemplo: `#/liga/la-liga/lideres`.

Dentro de cada competición, abre **Equipos y posiciones**. Las vistas incluyen clasificación, rankings y todos los clubes, con buscador y filtros General / Local / Visitante. Desde el escudo o nombre se abre la ficha del equipo con totales o promedios de goles, remates, tiros al arco, córners, tarjetas y faltas, a favor y en contra.

Las posiciones se consultan en football-data.org y conservan su fecha de consulta y orden del proveedor. Los promedios se calculan exclusivamente con los partidos registrados de esa competición en la temporada actual, con su propia fecha de corte. Los datos ausentes se excluyen de cada denominador. Si no hay clasificación del proveedor para un contexto, se muestra una tabla calculada, identificada como tal y sin atribuirle los desempates oficiales.

Para actualizar posiciones y reconstruir los agregados sin entrenar el modelo:

```powershell
python src/live_data/build_team_dashboard.py --refresh-standings
```

`run_pipeline.py` reconstruye los agregados; `--refresh-calendar` también actualiza las posiciones. No hay actualización automática en vivo. Los CSV originales y las predicciones se conservan.

Tres niveles de navegación: portada de competiciones, próximos partidos de una liga y análisis completo de un encuentro. Las rutas utilizan fragmentos (`#/liga/la-liga`, `#/partido/…`), de modo que las páginas se pueden compartir y recargar sin configuración especial del servidor.

## Abrir

En Windows, hacer doble clic en `Abrir_Web.cmd` en la raíz del proyecto. El lanzador abre el navegador e inicia un servidor local en segundo plano si hace falta. Utiliza la ubicación actual de la carpeta, incluso si se mueve. No publica la web en Internet.

Desde la raíz del proyecto:

```powershell
python -m http.server 8766 --bind 127.0.0.1 --directory web
```

Abrir http://127.0.0.1:8766. No abrir index.html directamente, porque los archivos JSON se cargan mediante fetch.

## Datos

- `data/predictions.json`: 1X2, marcadores, goles, estadísticas descriptivas, forma por ventanas, H2H, tendencias y procedencia. Lo actualiza `run_pipeline.py`.
- `data/fijas.json`: propuestas por mercado, tres niveles de riesgo, frecuencias recientes y combinadas de tres/cuatro partidos. Se genera automáticamente junto a las predicciones; `python src/live_data/recommendations.py` actualiza solo esta sección sin reentrenar.
- `data/assets.json`: relación explícita entre equipos, imágenes locales y sus URLs de origen.
- `assets/crests/`: 111 escudos de los equipos de las competiciones cubiertas.
- `assets/competitions/`: seis emblemas de competición.

Los escudos se descargaron de las URLs proporcionadas por football-data.org. Se conservan sus fuentes en el manifiesto. Para actualizarlos, ejecutar `python src/live_data/fetch_web_assets.py`, usando la credencial del entorno o `.env`. La clave solo se envía al dominio de la API; nunca a los servidores de imágenes ni al frontend.

La web emplea fuentes de Google Fonts con alternativas locales de sistema. Los escudos son locales y no dependen de solicitudes de imágenes a terceros durante la navegación.

## Comportamiento

Se filtran los próximos partidos por hora de inicio y se muestran horarios de Lima. Cada competición incluye búsqueda por equipo y filtros por fecha. El análisis contiene controles de forma (temporada, últimos 10/5/3), líneas de goles y metodología desplegable. El local se representa en verde, el empate en ocre y el visitante en violeta. Las estimaciones auxiliares mantienen su identificación y sus límites; no se modifican las probabilidades del modelo.

Si no hay encuentros, la web muestra un estado vacío. Si falta una imagen, muestra iniciales sin atribuir un escudo a otro club. Si el identificador de partido no existe, se ofrece volver a las competiciones. Las cadenas de datos se escriben con textContent, no como HTML.

`#/fijas` organiza propuestas por fecha de Lima. El explorador incluye resultado 1X2, doble oportunidad, hándicap, goles/resultado y goles, ambos marcan, remates, tiros al arco, faltas y córners totales/por equipo. Todos exigen mayoría reciente en ambas muestras, con cobertura mínima; se excluye 0,5 goles. Las tarjetas Betano se bloquean porque su liquidación difiere del CSV agregado. Los porcentajes usan texto pequeño. El comparador de cuota decimal distingue el precio teórico del umbral orientativo con descuento por sensibilidad; no hay garantía de rentabilidad. Las cuotas observadas llevan fuente y hora, las manuales se guardan solo en el navegador. No hay conexión automática de cuotas en vivo.

La web exige coincidencia de dataset y ejecución, calcula mercados conjuntos del mismo partido sin multiplicar marginales y retira iniciados de las combinadas. Si faltan tres o cuatro partidos admisibles muestra el motivo. Las propuestas y los mercados ampliados necesitan evaluación prospectiva propia.

La versión v3 prioriza los mercados de ganador, doble oportunidad, hándicap, ambos marcan y goles en cada nivel y selección por partido de las combinadas. Las estadísticas son complementarias. El explorador muestra primero «Resultado y goles» y después «Mercados complementarios». Cada muestra incluye su racha de aciertos consecutivos recientes. Esta selección no altera las probabilidades ni el modelo de goles validado.

No se ha añadido autenticación, pago ni publicación externa. La implementación actual es una web estática local.
