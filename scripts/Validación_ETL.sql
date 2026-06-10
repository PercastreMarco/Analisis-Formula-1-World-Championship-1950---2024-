-- =============================================================================
-- VALIDACIÓN POST CARGA
-- =============================================================================

SET search_path TO f1_dw;

SELECT
    p.nombre_completo,
    c.nombre        AS constructor,
    ci.nombre       AS circuito,
    t.anio,
    f.posicion_salida,
    f.posicion_final,
    f.puntos,
    f.delta_posicion,
    f.es_abandono
FROM fact_resultado_carrera f
JOIN dim_piloto      p  ON f.piloto_sk      = p.piloto_sk
JOIN dim_constructor c  ON f.constructor_sk = c.constructor_sk
JOIN dim_circuito    ci ON f.circuito_sk    = ci.circuito_sk
JOIN dim_tiempo      t  ON f.tiempo_sk      = t.tiempo_sk
ORDER BY t.anio DESC, f.puntos DESC
LIMIT 20;

