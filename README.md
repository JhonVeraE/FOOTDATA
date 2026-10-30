# FOOTDATA

Motor de probabilidades de fútbol para cinco ligas europeas y Champions.
Actualizado el 18 de octubre de 2026. Ejecutar con Python 3.11 o posterior.

## Ejecución

```powershell
python -m pip install -r requirements.txt
python run_pipeline.py
python run_pipeline.py --refresh-calendar
python run_pipeline.py --evaluate
python run_pipeline.py --excel
python -m unittest discover -s tests -v
python -m http.server 8765 --directory web
```

Abrir http://localhost:8765 para consultar la web local. El servidor es solo de desarrollo.
También puedes abrir `Abrir_Web.cmd` en Windows: utiliza la ubicación actual del proyecto e inicia la web local. El rediseño incluye portada de competiciones, próximos partidos con escudos y análisis completo por encuentro. Documentación del frontend: web/README.md.
Los comandos funcionan desde cualquier carpeta cuando se pasa la ruta completa del script.
La selección del modelo ya está guardada en data/artifacts/model_selection.json.
`--evaluate` reproduce la selección, calibración y comparación históricas; no hace falta ejecutarlo por cada partido.

## Datos y arquitectura

Los CSV originales se conservan en data/live. data_store.py valida y combina:

- match_stats_4ligas.csv: 8.908 encuentros históricos.
- match_stats_actualseason.csv: 341 encuentros de 2026/27, incluidos los 19 pronosticados del 18 de octubre.
- match_stats_champions_actualseason.csv: 36 encuentros de la fase liga 2026/27.

Total: 9.285 partidos, 18.570 filas por equipo. El cargador utiliza alias explícitos e IDs canónicos; detecta conflictos entre proveedores y comprueba reciprocidad. Las fechas sin hora se excluyen por día completo al aplicar un corte temporal. Los remates imposibles de West Ham–Newcastle del 15/08/2021 se ponen en cuarentena en memoria; no se altera el CSV. Un dato ausente no equivale a cero.

El historial UEFA sin fechas y Footiqo con semántica incompatible se conservan, pero no se mezclan automáticamente. Footiqo cuenta amarillas; este pipeline define tarjetas como amarillas + rojas. No existe una fuente de alineaciones/bajas integrada.

Flujo: fuentes → data_store → goal_model → full_report → JSON versionado → Excel/web/content_brief.
paths.py resuelve rutas desde el proyecto. run_pipeline.py coordina los pasos. Las entradas antiguas de Excel e hype usan ahora la misma ruta de predicción.

## Modelo

Poisson regularizado con ataque y defensa por club, intercepto y ventaja local por competición; pesos exponenciales por antigüedad en días. Corrección de marcadores bajos Dixon–Coles estimada después del ajuste de tasas, con dominio válido. No es una optimización conjunta de todos los parámetros Dixon–Coles. La identidad de club se comparte entre competiciones; las fuerzas de equipos con poca información se contraen hacia el promedio.

Selección en agosto de 2024–febrero de 2025: vida media 365 días, regularización 3, corrección de marcadores bajos activada. Temperatura 1,017 ajustada únicamente en marzo–mayo de 2025 para 1X2 doméstico. Se guardan probabilidades originales y ajustadas. No se aplica esa calibración a Champions. Elo se calcula como diagnóstico con información anterior al partido; no se utiliza como variable del modelo desplegado.

Las probabilidades de marcador, BTTS y líneas de goles se calculan mediante una matriz de distribución con cola adaptativa, sin simulación aleatoria ni agrupación de 8+ goles. Esos mercados proceden de la distribución original y todavía no tienen calibración específica. Las medias de córners, tarjetas, remates, tiros al arco y faltas domésticas usan ahora `venue-shrunk-count-v1`: forma ponderada por localía, ataque frente a defensa rival y contracción al promedio de liga por localía. Las probabilidades de sus distribuciones continúan sin calibración específica.

Los perfiles de temporada filtran la temporada efectiva del informe; últimos 10/5/3 describen forma. Los nulos se excluyen y se renormalizan pesos por variable. H2H se cuenta una vez y es descriptivo. Las tendencias dicen «subiendo/bajando», sin calificar como mejora el aumento de goles recibidos o tarjetas.

## Evaluación

Entrenamientos congelados al inicio de cada mes; ningún resultado de ese mes entra en el ajuste. Selección, calibración y evaluación ocupan periodos distintos. Referencias: frecuencias 1X2 previas de la liga y reconstrucción del método anterior con la misma información disponible. Los equipos sin antecedentes para la media anterior se excluyen solo de la comparación pareada, no de la evaluación total del nuevo modelo.

Resultados completos, curvas de fiabilidad por clase, conteos e intervalo bootstrap descriptivo: data/artifacts/evaluation.json. La revisión anterior ya examinó 500 partidos de 2025/26; esta es evidencia retrospectiva, no un historial de predicciones publicadas previamente. La calibración no garantiza mejora en cada periodo. La muestra europea es pequeña. El bootstrap por partido no modela dependencia temporal.

## Salidas y trazabilidad

- data/live/jornada_predictions.json: contrato por partido compatible con Excel.
- data/artifacts/prediction_run.json: fuentes, hashes, calidad, fecha de entrenamiento.
- data/artifacts/prediction_archive/: instantáneas nuevas por ejecución; no se reescribe el historial.
- data/artifacts/prospective_results.json: puntuación de la última predicción anterior al inicio por partido; se actualiza con los resultados disponibles. La revisión del 18/10/2026 incluye 19 partidos finalizados, con 13 aciertos de ganador/empate.
- data/artifacts/daily_reviews/2026-10-18/: pronósticos originales, resultados contrastados, estadísticas visibles de Sofascore y copias anteriores a la actualización. review_matchday.py valida la jornada y evita duplicados; no regenera pronósticos para puntuarlos.
- data/artifacts/evaluation.json y model_selection.json: protocolo, parámetros y resultados.
- data/artifacts/content_briefs.json: borradores de guion corto y puntos que requieren investigación. No publica ni envía mensajes.
- web/data/: copia pública de predicciones y evaluación; web/index.html las consume.
- data/artifacts/excel_partidos/: Excel, solo con --excel.

El calendario se actualiza desde football-data.org y se reconcilia con resultados propios. Por defecto se predice la siguiente jornada completa aún no iniciada por competición, junto con pendientes de jornadas anteriores con inicio futuro válido próximos a esa jornada. Se distinguen ambos grupos en web y JSON. `--nearest-only` conserva la selección de la jornada pendiente más cercana. No se inventan horas desconocidas. Los partidos cancelados o aplazados se excluyen hasta que exista un estado futuro válido. Brasil queda fuera de la cobertura predictiva actual.

### Actualización del 18 de octubre de 2026

Se reentrenó con 9.285 partidos y resultados hasta el 18/10. El corte exclusivo 19/10 admite resultados del día 18 únicamente si cada uno está contrastado como finalizado, con inicio pasado y marcador coincidente en el calendario original del proveedor. La fecha real de generación se conserva. Las previsiones anteriores siguen archivadas y la evaluación prospectiva selecciona solamente pronósticos anteriores al inicio.

Las cinco medias estadísticas domésticas superaron una validación temporal retrospectiva de 1.739 partidos de agosto de 2025 a junio de 2026, posterior a la selección de parámetros. El error absoluto por equipo bajó aproximadamente 1,54% en córners, 0,46% en tarjetas, 3,29% en remates, 2,02% en tiros al arco y 1,40% en faltas. El error del total de córners, remates y tiros al arco aumentó ligeramente dentro del límite fijado del 2%; no todas las métricas mejoran. Evidencia y protocolo: `count_model_selection.json`; reproducción: `evaluate_count_models.py`. Este cambio no se aplica a Champions.

Se descartó una corrección adicional de tasas de gol porque empeoró la validación separada de enero a junio de 2026 (950 partidos). Se conserva el método de goles y su calibración 1X2 anterior. Experimento: `goal_refinement.json` y `evaluate_goal_refinement.py`. Los resultados del 18/10 no se usaron para seleccionar estos ajustes.

Cobertura generada: 66 encuentros de próximas jornadas completas (La Liga 10, Premier 8, Bundesliga 7, Serie A 8, Ligue 1 8 y Champions 3), más cinco pendientes. La validación vectorizada del dataset conserva las comprobaciones de reciprocidad, valores nulos e identidades, con menor tiempo de carga.

## Credenciales y adquisición

Copiar .env.example a .env y configurar claves; .env está excluido por .gitignore. Las variables del entorno tienen prioridad. La credencial existente se trasladó del código a ese archivo local sin reproducirla en salidas. No se rotó la credencial. No subir .env ni copias antiguas con secretos.

refresh_calendar.py conserva la competición anterior si la respuesta falla o no corresponde a la temporada actual. API-Football queda como fuente opcional: su caché caduca y su contador usa UTC. No se ejecutó su backfill sin credencial; el pipeline principal no depende de él. FOOTBALL_SEASON_CODE permite seleccionar una temporada explícita para Datahub.

## Límites y siguientes pasos

### Fijas y combinadas

La ruta `#/fijas` usa `market-shortlist-v3`: conservadora (78–88%), normal (63–78%) y arriesgada (50–63%), con cuota teórica mínima 1,18. Todas las propuestas, incluidas las arriesgadas y el explorador, exigen mayoría estricta en ambas muestras, al menos tres observaciones por equipo y cinco encuentros únicos, sin duplicar H2H. No se completa un nivel sin respaldo. Se comparan hasta cinco partidos por equipo y localía; cuando faltan, se identifica expresamente el uso del historial general o la mezcla doméstica/europea en Champions. Las frecuencias no son probabilidades calibradas. No se recomienda la línea de 0,5 goles.

En cada nivel y selección por partido de las combinadas se priorizan ganador, doble oportunidad, hándicap, ambos marcan, goles y resultado con goles, siempre que superen los mismos filtros. Remates, tiros al arco, faltas y córners quedan como alternativas cuando falta una propuesta principal admisible. Así la cantidad de líneas estadísticas disponibles no desplaza los mercados principales por simple proximidad al porcentaje objetivo. La web muestra ambos grupos y la racha actual de aciertos de cada muestra. Esta prioridad no cambia el entrenamiento ni aumenta probabilidades: el modelo de goles validado y su calibración se conservan; el ajuste extra de tasas ya fue descartado por empeorar la validación temporal.

`recommendations.py` consume el contrato publicado sin reentrenarlo ni modificarlo y genera `web/data/fijas.json`, `data/artifacts/recommendations.json` y un archivo nuevo en `recommendation_archive/`. El generador principal lo ejecuta automáticamente. La web comprueba que dataset y ejecución coinciden antes de mostrarlo. Retira partidos iniciados y actualiza las combinadas cuando cambia la lista de futuros encuentros.

Mercados: resultado 1X2, doble oportunidad, hándicap asiático, goles totales/por equipo, ambos marcan, resultado combinado con goles, córners, remates, tiros al arco y faltas totales/por equipo. Los mercados de resultado y goles del mismo partido se calculan conjuntamente en la matriz, sin multiplicarlos. Para proyecciones estadísticas nuevas se usa la media ajustada por rival, con dispersión obtenida de al menos 30 observaciones históricas anteriores al corte por competición/localía. La muestra del rival compara lo concedido, no su producción ofensiva. Esas probabilidades y los criterios de selección aún necesitan evaluación prospectiva propia.

Betano define roja = 2 y excluye la segunda amarilla; el CSV agregado amarillas + rojas no permite reconstruirlo. Se excluyen recomendaciones de tarjetas Betano hasta disponer del desglose. Fuente: https://support.betano.pe/hc/es-pe/articles/36520716638877-Definiciones-de-mercados-de-f%C3%BAtbol . Los datos descriptivos originales de tarjetas se conservan.

El comparador permite introducir una cuota decimal Betano, sin enviar apuestas. Muestra cuota teórica 1/p y umbral orientativo 1,05/(p − descuento): 5 puntos para goles/resultado y 10 para conteos. Son hipótesis de sensibilidad elegidas, no una nueva calibración ni un intervalo de confianza. Superar ese umbral no confirma rentabilidad real. Las cuotas manuales quedan en el navegador, asociadas a ejecución, partido y selección.

Se revisaron las 532 sugerencias únicas de 71 encuentros el 19/10/2026, entre 01:03 y 01:19 Lima, mediante páginas públicas de Betano. Se encontraron 284 cuotas exactas: 25 superaban el umbral orientativo y 259 quedaban por debajo. Otras 248 no tenían una cuota exacta validada en la oferta consultada; esto no demuestra que el mercado no pueda publicarse después. La web conserva las selecciones y probabilidades originales y añade el estado de precio a cada una. Los datos no son cuotas en vivo ni implican rentabilidad confirmada.

Reproducción sin red: `python scripts/audit_visible_odds.py --targets data/artifacts/betano_audit_targets.json --frozen data/artifacts/recommendations_before_odds_audit.json --pages data/artifacts/betano_visible/20261019_audit`. El importador exige ambos equipos, orden local/visitante y hora exacta; distingue líneas, totales/equipos, primer tiempo, jugadores, hándicap asiático y europeo. Guarda las capturas visibles, fuente y hora; no inicia sesión ni coloca apuestas. `data/artifacts/betano_odds_audit.json` y `web/data/odds_audit.json` conservan los 532 estados. `betano_odds.json` contiene solo las 284 coincidencias. Una regeneración posterior de recomendaciones usa precios de hasta 15 minutos de antigüedad y sustituye esta auditoría congelada; se necesita una nueva consulta para auditar nuevas sugerencias.

Las combinadas utilizan 3 o 4 selecciones admisibles de partidos distintos sin repetir equipos, con muestra efectiva de al menos cinco y el mismo filtro de mayoría. Pueden incluir conteos; se mantienen las limitaciones de sus probabilidades. El producto supone independencia entre partidos y no está calibrado como mercado conjunto. Si faltan partidos se indica sin rellenar la lista. Su comparador requiere la cuota de la combinada exacta, que puede diferir del producto de cuotas individuales.

No se garantiza un porcentaje futuro de aciertos. Falta un historial prospectivo suficiente y validación independiente de córners, tarjetas, BTTS y goleadores. Lesiones, minutos, árbitros y alineaciones requieren fuentes propias y verificables. Las mejoras con remates, Elo u otras variables deben competir contra esta versión en una nueva validación temporal antes de publicarse.

La web es una consulta local de datos reales, sin cobros ni protección premium simulada. La web está publicada en https://footdataa.netlify.app y conectada a la rama main de GitHub mediante Netlify. Los cambios de la web se publican al subirlos al repositorio. Las nuevas predicciones y estadísticas requieren ejecutar el pipeline y subir los JSON generados; el hosting no ejecuta el modelo automáticamente.


## Automatización

El proyecto se actualiza solo en dos lugares, que se coordinan entre sí:

- **GitHub Actions** (`.github/workflows/`): `footdata-daily.yml` corre cada día a las 05:00 de Lima y `footdata-weekly.yml` los jueves a las 10:00 de Lima. Necesita el secret `FOOTBALL_DATA_KEY` en el repositorio (Settings → Secrets and variables → Actions). Solo publica en `main` si pasan todas las pruebas; Netlify redespliega con ese push.
- **PC con Windows** (`scripts/windows/`): `instalar_tareas.cmd` registra una vez las tareas *FOOTDATA\Diario* (06:30) y *FOOTDATA\Semanal* (jueves 10:30). Si GitHub Actions ya publicó ese día, la PC no repite el trabajo; si falló, la PC lo hace. Registros en `%LOCALAPPDATA%\FOOTDATA\logs`.

Comandos equivalentes:

    python run_pipeline.py --daily     # resultados y estadísticas finales, liquidación de fijas, web
    python run_pipeline.py --weekly    # calendario + diario + cuotas públicas + nuevos pronósticos y fijas

Reglas de la actualización diaria (`src/live_data/daily_update.py`):

1. Congela una sola vez, por fecha de Lima, la última publicación de pronósticos y fijas anterior al primer partido del día (desde `prediction_archive/` y `recommendation_archive/`).
2. Descarga de ESPN los scoreboards y boxscores de las seis competiciones de los últimos 3 días y guarda las respuestas en `data/artifacts/auto/raw/<fecha>/`.
3. Solo importa partidos en `STATUS_FULL_TIME` con remates, tiros a puerta, faltas, córners, amarillas y rojas. El marcador debe coincidir con football-data.org; sin clave o sin red se marca `espn_only`.
4. Todo lo dudoso (en juego, aplazado, estadística ausente, equipo sin alias, marcador discrepante o sin partido en el calendario) queda pendiente con su motivo y se reintenta al día siguiente. Nunca se inventa un dato ni un cero.
5. Es idempotente: un partido ya registrado (mismo ID, o mismos equipos y liga con un día de margen) no se vuelve a añadir. Si la base tiene otro valor (por ejemplo, de Sofascore) se conserva y la diferencia queda en el informe.
6. Liquida las fijas con las instantáneas congeladas y actualiza el seguimiento prospectivo, las tablas y la web. El informe de cada ejecución queda en `data/artifacts/auto/<fecha>/run_report.json`.

Sofascore no admite clientes automáticos. Sirve como contraste manual: `src/live_data/sofascore_capture.py` convierte una captura (evento, estadísticas e incidencias) a las mismas métricas y `--sofascore-dir` compara con ESPN.
