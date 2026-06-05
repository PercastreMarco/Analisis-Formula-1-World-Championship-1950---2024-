--- Query 1 — Verificar las 6 tablas:

SELECT table_name, obj_description(
    (quote_ident(table_schema)||'.'||quote_ident(table_name))::regclass, 'pg_class'
) AS descripcion
FROM information_schema.tables
WHERE table_schema = 'f1_dw'
ORDER BY table_name;


--- Query 2 — Verificar los 7 índices:

SELECT indexname, tablename
FROM pg_indexes
WHERE schemaname = 'f1_dw'
ORDER BY tablename, indexname;

--- Query 3 — Verificar las foreign keys de la fact table:

SELECT
    kcu.column_name        AS columna_fk,
    ccu.table_name         AS tabla_dimension,
    ccu.column_name        AS columna_pk
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
    ON tc.constraint_name = kcu.constraint_name
    AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage AS ccu
    ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_schema = 'f1_dw'
  AND tc.table_name = 'fact_resultado_carrera'
ORDER BY kcu.column_name;
