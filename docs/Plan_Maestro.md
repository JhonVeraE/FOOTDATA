# Plan Maestro FOOTDATA

Revisión del 26 de octubre de 2026. Cobertura: La Liga, Premier League, Bundesliga, Serie A, Ligue 1 y Champions.

## Actualización del 26 de octubre

La base reúne 9.356 partidos únicos, incluidos 394 encuentros actuales de las cinco ligas y 54 de Champions. Se completaron los 22 partidos del domingo 25 y los dos del lunes 26. El modelo se reentrena con resultados verificados hasta el 26; conserva los hiperparámetros que ya superaron la evaluación temporal. Se generan las próximas jornadas completas: 48 partidos de ligas y 18 de Champions.

Las fijas incorporan revisión por familia de mercado y por selección del equipo. El historial modifica el orden de alternativas y puede bloquear repeticiones tras dos fallos recientes, pero no sustituye las probabilidades del modelo por porcentajes de rachas. Para conservadoras y combinadas se exige cumplimiento en al menos dos de los tres partidos más recientes de ambas muestras. Una elección sin respaldo queda vacía.

El filtro de recencia se auditó sobre las selecciones originales del 23 al 26: conserva 43 de 48 conservadoras, con 36 aciertos, frente a 40 de 48 sin el filtro. La diferencia de porcentaje es pequeña; no demuestra una mejora sólida de precisión, no evalúa las alternativas sustitutas ni justifica aumentar las probabilidades. La memoria por mercado queda en seguimiento prospectivo. Los resultados y probabilidades anteriores se archivan sin reescritura.

La web está publicada en Netlify y los videos piloto con narración y música original ya existen. Las fases siguientes describen la hoja de ruta histórica; estas actualizaciones prevalecen sobre sus estados antiguos.

## Estado comprobado

- Integración de los CSV históricos y actuales: implementada; 9.266 partidos únicos.
- Validación temporal, identidades, nulos y procedencia: implementada.
- Modelo de ataque/defensa regularizado y corrección de marcadores bajos: implementado y comparado retrospectivamente.
- Calibración 1X2 doméstica en periodo independiente: implementada; revisar curvas y muestras antes de extrapolar.
- Calendario actual y predicciones futuras: actualizados; 41 partidos en la primera ejecución de esta versión.
- JSON común, archivo de predicciones, Excel, borradores de contenido y web local: conectados.
- Modelos específicos de córners/tarjetas y calibración de esos mercados: pendientes; se muestran solo estimaciones identificadas.
- Alineaciones, bajas, árbitros y goleador probable: sin fuentes/modelo integrado validado.
- Video final, voz/música, publicación, dominio y monetización: pendientes.

## Fase 0 · Mantener datos y medir resultados reales

1. Actualizar el calendario con run_pipeline.py --refresh-calendar.
2. Incorporar estadísticas nuevas con el mismo contrato y sus fuentes. Comprobar duplicados, tarjetas y fechas.
3. Ejecutar el pipeline; conservar instantáneas anteriores a los partidos.
4. Evaluar el archivo prospectivo sin reescribir probabilidades después del resultado.
5. Revisar cobertura de equipos y competiciones, calibración y estabilidad por temporada.

No llamar «terminado» al modelo. Sus parámetros actuales tienen evidencia retrospectiva favorable; falta comprobar mantenimiento de resultados futuros.

## Fase 1 · Investigación de mejoras

Comparar futuras variables (remates previos, tiros al arco, Elo, descanso) con validación temporal y un nuevo periodo de aceptación. No se añaden por intuición. Validar distribuciones específicas para córners/tarjetas y sus intervalos. Para Champions, ampliar historial fechado y evaluar calibración propia; dos jornadas no bastan para proclamar precisión estable.

## Fase 2 · Contenido piloto

content_brief.py genera borradores a partir del JSON común. Mantener investigación manual de bajas y alineaciones con fuente y hora. Usar las mismas probabilidades en web, Excel y guion. Producir primero piezas piloto; revisar texto y datos antes de crear video/voz/música. Medir utilidad del contenido sin prometer «fijas» ni «certeza IA».

## Fase 3 · Web pública

La web local ya lee web/data/predictions.json y muestra evaluación y procedencia. Validar accesibilidad y móvil, elegir hosting y dominio, y publicar cuando el responsable lo solicite. Sin secreto ni claves en frontend. No existe todavía un sistema de pago; el desenfoque CSS no se considera control de acceso.

## Fase 4 · Comunidad y monetización

Definir identidad y cuentas, probar audiencia y publicar un historial de aciertos y errores completo. Decidir después qué análisis aporta la membresía y su precio. Si se protege información en la web, implementar autenticación y autorización en servidor; nunca enviar datos restringidos a quien no tenga acceso.

## Comandos y documentación

Consultar README.md para arquitectura, comandos, metodología y límites. requirements-tested.txt registra el entorno utilizado; tests/test_pipeline.py protege los comportamientos críticos. data/artifacts/evaluation.json contiene resultados completos, incluidos tamaños de muestra y comparación pareada.
