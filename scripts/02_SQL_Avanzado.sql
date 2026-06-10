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
-- Pregunta : ¿Cuál es el ranking acumulado de puntos por piloto dentro de
--            cada temporada y quién lidera el campeonato en cada ronda?
-- Funciones: SUM() OVER, LAG(), RANK() OVER
-- Corrección: RANK() no puede anidar otra window function en su ORDER BY.
--             Se separa en 3 CTEs: puntos_por_ronda → acumulado → con_ranking.
-- =============================================================================

WITH puntos_por_ronda AS (
    -- Paso 1: puntos individuales por piloto y ronda
    SELECT
        t.temporada,
        t.numero_ronda,
        t.nombre_gp,
        p.nombre_completo                                   AS piloto,
        c.nombre                                            AS constructor,
        f.puntos
    FROM fact_resultado_carrera f
    JOIN dim_piloto      p ON f.piloto_sk      = p.piloto_sk
    JOIN dim_constructor c ON f.constructor_sk = c.constructor_sk
    JOIN dim_tiempo      t ON f.tiempo_sk      = t.tiempo_sk
    WHERE t.temporada = 2023
),
acumulado AS (
    -- Paso 2: puntos acumulados y puntos de la ronda anterior
    --         SUM() OVER y LAG() se calculan aquí — sin anidar
    SELECT
        temporada,
        numero_ronda,
        nombre_gp,
        piloto,
        constructor,
        puntos,
        SUM(puntos) OVER (
            PARTITION BY temporada, piloto
            ORDER BY numero_ronda
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )                                                   AS puntos_acumulados,
        LAG(puntos, 1, 0) OVER (
            PARTITION BY temporada, piloto
            ORDER BY numero_ronda
        )                                                   AS puntos_ronda_anterior
    FROM puntos_por_ronda
),
con_ranking AS (
    -- Paso 3: RANK() sobre puntos_acumulados ya calculados en el paso anterior
    SELECT
        temporada,
        numero_ronda,
        nombre_gp,
        piloto,
        constructor,
        puntos,
        puntos_acumulados,
        puntos_ronda_anterior,
        RANK() OVER (
            PARTITION BY temporada, numero_ronda
            ORDER BY puntos_acumulados DESC
        )                                                   AS posicion_campeonato
    FROM acumulado
)
SELECT
    numero_ronda,
    nombre_gp,
    piloto,
    constructor,
    puntos                                                  AS puntos_ronda,
    puntos_acumulados,
    posicion_campeonato,
    puntos - puntos_ronda_anterior                          AS variacion_vs_ronda_anterior
FROM con_ranking
WHERE posicion_campeonato <= 5              -- Top 5 del campeonato en cada ronda
ORDER BY numero_ronda, posicion_campeonato;


-- =============================================================================
-- TÉCNICA 2 — CTEs ANIDADOS (3 niveles)
-- Pregunta : ¿Qué constructores tienen mayor eficiencia (posicion salida vs
--            llegada) y menor tasa de abandono mecánico por era histórica?
-- Niveles  : base → metricas_constructor → ranking_eficiencia
-- =============================================================================

WITH base AS (
    -- Nivel 1: join de fact con dims relevantes, filtrar grids válidos
    SELECT
        c.nombre                                            AS constructor,
        c.era_f1,
        f.posicion_salida,
        f.posicion_final,
        f.delta_posicion,
        f.es_abandono,
        e.categoria                                         AS categoria_estado
    FROM fact_resultado_carrera f
    JOIN dim_constructor c ON f.constructor_sk = c.constructor_sk
    JOIN dim_estado      e ON f.estado_sk      = e.estado_sk
    WHERE f.posicion_salida IS NOT NULL
      AND f.posicion_salida > 0
),
metricas_constructor AS (
    -- Nivel 2: métricas agregadas por constructor y era
    SELECT
        constructor,
        era_f1,
        COUNT(*)                                            AS total_entradas,
        ROUND(AVG(delta_posicion)::NUMERIC, 2)              AS avg_delta_posicion,
        ROUND(
            SUM(CASE WHEN NOT es_abandono THEN 1 ELSE 0 END)::NUMERIC
            / NULLIF(COUNT(*), 0) * 100
        , 1)                                                AS pct_finalizados,
        ROUND(
            SUM(CASE WHEN categoria_estado = 'Abandono mecanico'
                THEN 1 ELSE 0 END)::NUMERIC
            / NULLIF(COUNT(*), 0) * 100
        , 1)                                                AS pct_abandono_mecanico,
        SUM(CASE WHEN posicion_final = 1 THEN 1 ELSE 0 END) AS victorias
    FROM base
    GROUP BY constructor, era_f1
    HAVING COUNT(*) >= 20       -- Mínimo 20 entradas para relevancia estadística
),
ranking_eficiencia AS (
    -- Nivel 3: RANK() sobre las métricas calculadas en el nivel anterior
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
        )                                                   AS rank_eficiencia_era
    FROM metricas_constructor
)
SELECT
    era_f1,
    rank_eficiencia_era                                     AS rank,
    constructor,
    total_entradas,
    avg_delta_posicion,
    pct_finalizados                                         AS pct_termina,
    pct_abandono_mecanico                                   AS pct_falla_mecanica,
    victorias
FROM ranking_eficiencia
WHERE rank_eficiencia_era <= 3              -- Top 3 más eficientes por era
ORDER BY era_f1, rank_eficiencia_era;


-- =============================================================================
-- TÉCNICA 3 — PERCENTILE_CONT (función de orden de conjunto)
-- Pregunta : ¿Desde qué posición de salida mediana se gana en cada circuito
--            y qué dispersión existe entre el p25 y p75?
-- Función  : PERCENTILE_CONT(f) WITHIN GROUP (ORDER BY col)
-- =============================================================================

WITH ganadores AS (
    SELECT
        ci.nombre                                           AS circuito,
        ci.pais,
        f.posicion_salida
    FROM fact_resultado_carrera f
    JOIN dim_circuito ci ON f.circuito_sk = ci.circuito_sk
    WHERE f.posicion_final  = 1
      AND f.posicion_salida IS NOT NULL
      AND f.posicion_salida > 0
)
SELECT
    circuito,
    pais,
    COUNT(*)                                                AS total_ganadores,
    PERCENTILE_CONT(0.5)  WITHIN GROUP (ORDER BY posicion_salida) AS mediana_grid,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY posicion_salida) AS p25_grid,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY posicion_salida) AS p75_grid,
    ROUND(
        SUM(CASE WHEN posicion_salida = 1 THEN 1 ELSE 0 END)::NUMERIC
        / NULLIF(COUNT(*), 0) * 100
    , 1)                                                    AS pct_gana_desde_pole,
    MIN(posicion_salida)                                    AS mejor_grid_ganador,
    MAX(posicion_salida)                                    AS peor_grid_ganador
FROM ganadores
GROUP BY circuito, pais
HAVING COUNT(*) >= 5                        -- Mínimo 5 ediciones del GP
ORDER BY mediana_grid ASC;                  -- Circuitos donde más importa la pole


-- =============================================================================
-- TÉCNICA 4 — FUNCIONES DE FECHA + WINDOW FUNCTIONS
-- Pregunta : ¿Cómo evoluciona la edad promedio de los ganadores de carrera
--            por temporada y era? ¿La F1 moderna premia a pilotos más jóvenes?
-- Funciones: DATE_PART(), AGE(), LAG() OVER, PERCENTILE_CONT()
-- Corrección: LAG() no puede aplicarse directamente sobre una expresión
--             agregada en el SELECT. Se resuelve con un CTE intermedio
--             que materializa avg_edad antes de aplicar LAG().
-- =============================================================================

WITH edad_ganadores AS (
    -- Paso 1: calcular edad de cada piloto en cada carrera que ganó
    SELECT
        t.temporada,
        t.era_f1,
        DATE_PART('year', AGE(t.fecha, p.fecha_nacimiento)) AS edad_en_carrera
    FROM fact_resultado_carrera f
    JOIN dim_piloto p ON f.piloto_sk = p.piloto_sk
    JOIN dim_tiempo t ON f.tiempo_sk = t.tiempo_sk
    WHERE f.posicion_final      = 1
      AND p.fecha_nacimiento IS NOT NULL
      AND t.fecha            IS NOT NULL
),
agregado_temporada AS (
    -- Paso 2: agregar por temporada — materializa avg_edad antes del LAG()
    SELECT
        era_f1,
        temporada,
        COUNT(*)                                            AS carreras_ganadas,
        ROUND(AVG(edad_en_carrera)::NUMERIC, 1)             AS avg_edad,
        MIN(edad_en_carrera)                                AS edad_minima,
        MAX(edad_en_carrera)                                AS edad_maxima,
        PERCENTILE_CONT(0.5) WITHIN GROUP (
            ORDER BY edad_en_carrera
        )                                                   AS mediana_edad
    FROM edad_ganadores
    GROUP BY era_f1, temporada
)
-- Paso 3: aplicar LAG() sobre avg_edad ya materializado
SELECT
    era_f1,
    temporada,
    carreras_ganadas,
    avg_edad,
    edad_minima,
    edad_maxima,
    mediana_edad,
    avg_edad - LAG(avg_edad) OVER (
        ORDER BY temporada
    )                                                       AS variacion_edad_vs_anterior
FROM agregado_temporada
ORDER BY temporada;


-- =============================================================================
-- TÉCNICA 5 — STORED PROCEDURE
-- Propósito: Genera resumen de dominancia por constructor para cualquier
--            temporada. Reutilizable desde el dashboard o scripts externos.
-- Uso      : CALL f1_dw.resumen_temporada(2023);
-- Corrección: RANK() OVER no puede usarse directamente en CREATE TABLE AS
--             con GROUP BY. Se separa en tabla temporal + query final con RANK().
-- =============================================================================

CREATE OR REPLACE PROCEDURE f1_dw.resumen_temporada(p_temporada INT)
LANGUAGE plpgsql
AS $$
DECLARE
    v_count INT;
BEGIN
    RAISE NOTICE '================================================';
    RAISE NOTICE 'Resumen Temporada: %', p_temporada;
    RAISE NOTICE '================================================';

    -- Verificar que la temporada tiene datos antes de continuar
    SELECT COUNT(*) INTO v_count
    FROM fact_resultado_carrera f
    JOIN dim_tiempo t ON f.tiempo_sk = t.tiempo_sk
    WHERE t.temporada = p_temporada;

    IF v_count = 0 THEN
        RAISE EXCEPTION 'No se encontraron datos para la temporada %', p_temporada;
    END IF;

    -- Tabla temporal con agregados por constructor (sin RANK para evitar error)
    DROP TABLE IF EXISTS tmp_resumen;
    CREATE TEMP TABLE tmp_resumen AS
    SELECT
        c.nombre                                            AS constructor,
        c.era_f1,
        COUNT(*)                                            AS entradas,
        SUM(f.puntos)                                       AS puntos_totales,
        SUM(CASE WHEN f.posicion_final = 1  THEN 1 ELSE 0 END) AS victorias,
        SUM(CASE WHEN f.posicion_final <= 3 THEN 1 ELSE 0 END) AS podios,
        ROUND(AVG(f.posicion_final)::NUMERIC, 1)            AS avg_pos_final,
        SUM(CASE WHEN f.es_abandono THEN 1 ELSE 0 END)      AS abandonos
    FROM fact_resultado_carrera f
    JOIN dim_constructor c ON f.constructor_sk = c.constructor_sk
    JOIN dim_tiempo      t ON f.tiempo_sk      = t.tiempo_sk
    WHERE t.temporada = p_temporada
    GROUP BY c.nombre, c.era_f1;

    RAISE NOTICE 'Datos cargados: % constructores en temporada %',
        (SELECT COUNT(*) FROM tmp_resumen), p_temporada;
    RAISE NOTICE 'Ejecutar: SELECT * FROM tmp_resumen ORDER BY puntos_totales DESC;';

END;
$$;

-- Consulta equivalente directa — mismos resultados sin necesidad del CALL
-- Cambiar el año en el WHERE para cualquier temporada
SELECT
    c.nombre                                                AS constructor,
    c.era_f1,
    COUNT(*)                                                AS entradas,
    SUM(f.puntos)                                           AS puntos_totales,
    SUM(CASE WHEN f.posicion_final = 1  THEN 1 ELSE 0 END)  AS victorias,
    SUM(CASE WHEN f.posicion_final <= 3 THEN 1 ELSE 0 END)  AS podios,
    ROUND(AVG(f.posicion_final)::NUMERIC, 1)                AS avg_pos_final,
    SUM(CASE WHEN f.es_abandono THEN 1 ELSE 0 END)          AS abandonos,
    RANK() OVER (ORDER BY SUM(f.puntos) DESC)               AS posicion_campeonato
FROM fact_resultado_carrera f
JOIN dim_constructor c ON f.constructor_sk = c.constructor_sk
JOIN dim_tiempo      t ON f.tiempo_sk      = t.tiempo_sk
WHERE t.temporada = 2023
GROUP BY c.nombre, c.era_f1
ORDER BY posicion_campeonato;

-- =============================================================================
-- FIN DEL ARCHIVO
-- Resumen de técnicas aplicadas:
--   Técnica 1 — Window Functions : SUM() OVER, LAG(), RANK() OVER (3 CTEs)
--   Técnica 2 — CTEs anidados    : 3 niveles base→metricas→ranking
--   Técnica 3 — PERCENTILE_CONT  : p25, p50, p75 con WITHIN GROUP
--   Técnica 4 — Funciones fecha  : DATE_PART(), AGE() + LAG() (2 CTEs)
--   Técnica 5 — Stored Procedure : CALL resumen_temporada(año)
-- =============================================================================
