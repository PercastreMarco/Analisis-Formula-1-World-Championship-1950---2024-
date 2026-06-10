-- =============================================================================
-- Proyecto Final — Módulo 4: Inteligencia de Negocios y SQL Avanzado
-- Archivo   : 02_SQL_Avanzado.sql
-- Propósito : Consultas analíticas con SQL avanzado sobre el modelo dimensional
-- Schema    : f1_dw  (Aurora PostgreSQL)
-- Técnicas  : 1. Window Functions  2. CTEs  3. PERCENTILE_CONT
--             4. Funciones de fecha  5. Stored Procedure
-- =============================================================================

SET search_path TO f1_dw;

-- =============================================================================
-- TÉCNICA 1 — WINDOW FUNCTIONS
-- Pregunta: ¿Cuál es el ranking acumulado de puntos por piloto dentro de
--           cada temporada, y quién lidera en cada ronda?
-- Funciones: RANK(), SUM() OVER, LAG()
-- =============================================================================

WITH puntos_por_ronda AS (
    SELECT
        t.temporada,
        t.numero_ronda,
        t.nombre_gp,
        p.nombre_completo                               AS piloto,
        c.nombre                                        AS constructor,
        f.puntos
    FROM fact_resultado_carrera f
    JOIN dim_piloto      p ON f.piloto_sk      = p.piloto_sk
    JOIN dim_constructor c ON f.constructor_sk = c.constructor_sk
    JOIN dim_tiempo      t ON f.tiempo_sk      = t.tiempo_sk
    WHERE t.temporada = 2023
),
acumulado AS (
    SELECT
        temporada,
        numero_ronda,
        nombre_gp,
        piloto,
        constructor,
        puntos,
        -- Puntos acumulados en la temporada hasta esta ronda
        SUM(puntos) OVER (
            PARTITION BY temporada, piloto
            ORDER BY numero_ronda
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )                                               AS puntos_acumulados,
        -- Ranking en cada ronda por puntos acumulados
        RANK() OVER (
            PARTITION BY temporada, numero_ronda
            ORDER BY SUM(puntos) OVER (
                PARTITION BY temporada, piloto
                ORDER BY numero_ronda
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) DESC
        )                                               AS posicion_campeonato,
        -- Puntos en la ronda anterior (para calcular tendencia)
        LAG(puntos, 1, 0) OVER (
            PARTITION BY temporada, piloto
            ORDER BY numero_ronda
        )                                               AS puntos_ronda_anterior
    FROM puntos_por_ronda
)
SELECT
    numero_ronda,
    nombre_gp,
    piloto,
    constructor,
    puntos,
    puntos_acumulados,
    posicion_campeonato,
    puntos - puntos_ronda_anterior                      AS variacion_vs_ronda_anterior
FROM acumulado
WHERE posicion_campeonato <= 5          -- Top 5 del campeonato en cada ronda
ORDER BY numero_ronda, posicion_campeonato;


-- =============================================================================
-- TÉCNICA 2 — CTEs (Common Table Expressions)
-- Pregunta: ¿Qué constructores tienen mayor eficiencia de conversión
--           (posición en clasificación vs posición en carrera) y menor
--           tasa de abandono mecánico por era?
-- =============================================================================

WITH base AS (
    -- Base: resultados con categoría de estado
    SELECT
        c.nombre                                        AS constructor,
        c.era_f1,
        f.posicion_salida,
        f.posicion_final,
        f.delta_posicion,
        f.es_abandono,
        e.categoria                                     AS categoria_estado
    FROM fact_resultado_carrera f
    JOIN dim_constructor c ON f.constructor_sk = c.constructor_sk
    JOIN dim_estado      e ON f.estado_sk      = e.estado_sk
    WHERE f.posicion_salida IS NOT NULL
      AND f.posicion_salida > 0
),
metricas_constructor AS (
    -- Métricas agregadas por constructor y era
    SELECT
        constructor,
        era_f1,
        COUNT(*)                                        AS total_entradas,
        ROUND(AVG(delta_posicion)::NUMERIC, 2)          AS avg_delta_posicion,
        ROUND(
            SUM(CASE WHEN NOT es_abandono THEN 1 ELSE 0 END)::NUMERIC
            / COUNT(*) * 100, 1
        )                                               AS pct_finalizados,
        ROUND(
            SUM(CASE WHEN categoria_estado = 'Abandono mecanico'
                THEN 1 ELSE 0 END)::NUMERIC
            / COUNT(*) * 100, 1
        )                                               AS pct_abandono_mecanico,
        SUM(CASE WHEN posicion_final = 1 THEN 1 ELSE 0 END)
                                                        AS victorias
    FROM base
    GROUP BY constructor, era_f1
    HAVING COUNT(*) >= 20           -- Mínimo 20 entradas para ser estadísticamente relevante
),
ranking_eficiencia AS (
    -- Ranking de eficiencia dentro de cada era
    SELECT
        constructor,
        era_f1,
        total_entradas,
        avg_delta_posicion,
        pct_finalizados,
        pct_abandono_mecanico,
        victorias,
        RANK() OVER (
            PARTITION BY era_f1
            ORDER BY pct_finalizados DESC, avg_delta_posicion DESC
        )                                               AS rank_eficiencia_era
    FROM metricas_constructor
)
SELECT
    era_f1,
    rank_eficiencia_era                                 AS rank,
    constructor,
    total_entradas,
    avg_delta_posicion,
    pct_finalizados                                     AS pct_termina,
    pct_abandono_mecanico                               AS pct_falla_mecanica,
    victorias
FROM ranking_eficiencia
WHERE rank_eficiencia_era <= 3          -- Top 3 por era
ORDER BY era_f1, rank_eficiencia_era;


-- =============================================================================
-- TÉCNICA 3 — PERCENTILE_CONT (función predefinida no trivial)
-- Pregunta: ¿Cuál es la distribución estadística de posiciones de salida
--           para los ganadores de cada circuito? ¿Desde qué posición
--           mediana se gana en cada pista?
-- =============================================================================

WITH ganadores AS (
    SELECT
        ci.nombre                                       AS circuito,
        ci.pais,
        f.posicion_salida,
        f.puntos,
        f.delta_posicion,
        t.temporada
    FROM fact_resultado_carrera f
    JOIN dim_circuito ci ON f.circuito_sk = ci.circuito_sk
    JOIN dim_tiempo   t  ON f.tiempo_sk   = t.tiempo_sk
    WHERE f.posicion_final = 1
      AND f.posicion_salida IS NOT NULL
      AND f.posicion_salida > 0
)
SELECT
    circuito,
    pais,
    COUNT(*)                                            AS total_carreras,
    -- Mediana de posición de salida de los ganadores
    PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY posicion_salida
    )                                                   AS mediana_grid_ganador,
    -- Percentil 25 y 75 para ver dispersión
    PERCENTILE_CONT(0.25) WITHIN GROUP (
        ORDER BY posicion_salida
    )                                                   AS p25_grid_ganador,
    PERCENTILE_CONT(0.75) WITHIN GROUP (
        ORDER BY posicion_salida
    )                                                   AS p75_grid_ganador,
    -- % de victorias desde la pole position
    ROUND(
        SUM(CASE WHEN posicion_salida = 1 THEN 1 ELSE 0 END)::NUMERIC
        / COUNT(*) * 100, 1
    )                                                   AS pct_victoria_desde_pole,
    MIN(posicion_salida)                                AS mejor_grid_ganador,
    MAX(posicion_salida)                                AS peor_grid_ganador
FROM ganadores
GROUP BY circuito, pais
HAVING COUNT(*) >= 5                    -- Mínimo 5 ediciones del GP
ORDER BY mediana_grid_ganador ASC;      -- Circuitos donde la pole más importa


-- =============================================================================
-- TÉCNICA 4 — FUNCIONES DE FECHA + WINDOW FUNCTIONS
-- Pregunta: ¿Cómo evoluciona la edad promedio de los campeones y ganadores
--           de carreras por era? ¿Los pilotos son más jóvenes o mayores
--           en la era moderna?
-- =============================================================================

WITH edad_ganadores AS (
    SELECT
        p.nombre_completo                               AS piloto,
        p.fecha_nacimiento,
        t.fecha                                         AS fecha_carrera,
        t.temporada,
        t.era_f1,
        f.posicion_final,
        f.puntos,
        -- Edad del piloto en el momento de la carrera
        DATE_PART('year', AGE(t.fecha, p.fecha_nacimiento))
                                                        AS edad_en_carrera
    FROM fact_resultado_carrera f
    JOIN dim_piloto  p ON f.piloto_sk  = p.piloto_sk
    JOIN dim_tiempo  t ON f.tiempo_sk  = t.tiempo_sk
    WHERE f.posicion_final = 1
      AND p.fecha_nacimiento IS NOT NULL
      AND t.fecha IS NOT NULL
)
SELECT
    era_f1,
    temporada,
    COUNT(*)                                            AS victorias_con_edad,
    ROUND(AVG(edad_en_carrera)::NUMERIC, 1)             AS edad_promedio_ganador,
    MIN(edad_en_carrera)                                AS edad_minima_ganador,
    MAX(edad_en_carrera)                                AS edad_maxima_ganador,
    PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY edad_en_carrera
    )                                                   AS mediana_edad,
    -- Tendencia: diferencia vs temporada anterior
    ROUND(AVG(edad_en_carrera)::NUMERIC, 1)
    - LAG(ROUND(AVG(edad_en_carrera)::NUMERIC, 1)) OVER (
        ORDER BY temporada
    )                                                   AS variacion_edad_vs_temporada_anterior
FROM edad_ganadores
GROUP BY era_f1, temporada
ORDER BY temporada;


-- =============================================================================
-- TÉCNICA 5 — STORED PROCEDURE
-- Propósito: Genera un resumen de dominancia por constructor para una
--            temporada específica. Reutilizable desde el dashboard o ETL.
-- Uso      : CALL f1_dw.resumen_temporada(2023);
-- =============================================================================

CREATE OR REPLACE PROCEDURE f1_dw.resumen_temporada(p_temporada INT)
LANGUAGE plpgsql
AS $$
BEGIN
    -- Resumen de puntos y victorias por constructor en la temporada
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Resumen Temporada %', p_temporada;
    RAISE NOTICE '========================================';

    -- Tabla temporal con resultados de la temporada
    CREATE TEMP TABLE IF NOT EXISTS tmp_resumen_temporada ON COMMIT DROP AS
    SELECT
        c.nombre                                        AS constructor,
        c.era_f1,
        COUNT(*)                                        AS carreras,
        SUM(f.puntos)                                   AS puntos_totales,
        SUM(CASE WHEN f.posicion_final = 1 THEN 1 ELSE 0 END)
                                                        AS victorias,
        SUM(CASE WHEN f.posicion_final <= 3 THEN 1 ELSE 0 END)
                                                        AS podios,
        ROUND(AVG(f.posicion_final)::NUMERIC, 1)        AS avg_posicion_final,
        SUM(CASE WHEN f.es_abandono THEN 1 ELSE 0 END)  AS abandonos,
        RANK() OVER (ORDER BY SUM(f.puntos) DESC)       AS posicion_campeonato
    FROM fact_resultado_carrera f
    JOIN dim_constructor c ON f.constructor_sk = c.constructor_sk
    JOIN dim_tiempo      t ON f.tiempo_sk      = t.tiempo_sk
    WHERE t.temporada = p_temporada
    GROUP BY c.nombre, c.era_f1;

    -- Mostrar resultado
    RAISE NOTICE 'Constructor | Puntos | Victorias | Podios | Avg Pos | Abandonos';
    RAISE NOTICE '--------------------------------------------------------------';

    -- Verificar que la temporada tiene datos
    IF NOT EXISTS (SELECT 1 FROM tmp_resumen_temporada) THEN
        RAISE EXCEPTION 'No se encontraron datos para la temporada %', p_temporada;
    END IF;

END;
$$;

-- Consulta equivalente reutilizable (compatible con DBeaver y Colab)
-- Uso: reemplaza p_temporada con el año deseado
SELECT
    c.nombre                                            AS constructor,
    c.era_f1,
    COUNT(*)                                            AS entradas,
    SUM(f.puntos)                                       AS puntos_totales,
    SUM(CASE WHEN f.posicion_final = 1  THEN 1 ELSE 0 END) AS victorias,
    SUM(CASE WHEN f.posicion_final <= 3 THEN 1 ELSE 0 END) AS podios,
    ROUND(AVG(f.posicion_final)::NUMERIC, 1)            AS avg_posicion_final,
    SUM(CASE WHEN f.es_abandono THEN 1 ELSE 0 END)      AS abandonos,
    RANK() OVER (ORDER BY SUM(f.puntos) DESC)           AS posicion_campeonato
FROM fact_resultado_carrera f
JOIN dim_constructor c ON f.constructor_sk = c.constructor_sk
JOIN dim_tiempo      t ON f.tiempo_sk      = t.tiempo_sk
WHERE t.temporada = 2023           -- Cambiar año aquí
GROUP BY c.nombre, c.era_f1
ORDER BY posicion_campeonato;

-- =============================================================================
-- FIN DEL ARCHIVO
-- Técnicas cubiertas:
--   1. Window Functions : RANK(), SUM() OVER, LAG()         — Técnica 1 y 4
--   2. CTEs             : WITH anidados de 3 niveles        — Técnica 2
--   3. PERCENTILE_CONT  : p25, p50, p75 de grid ganadores   — Técnica 3
--   4. Funciones fecha  : DATE_PART, AGE                    — Técnica 4
--   5. Stored Procedure : CALL resumen_temporada(año)       — Técnica 5
-- =============================================================================
