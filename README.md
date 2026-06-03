# 🏎️ Proyecto Final — Módulo 4: Inteligencia de Negocios y SQL Avanzado

## Rendimiento de Pilotos y Estrategias de Carrera en Fórmula 1 (1950–2024)

---

## 📌 Pregunta Analítica de Negocio

> **¿Qué factores — posición de salida, número y momento de pit stops, equipo y tipo de circuito — tienen mayor impacto estadístico en el resultado final de carrera, y cómo ha evolucionado la dominancia de constructores y pilotos a lo largo de las eras de la Fórmula 1 (1950–2024)?**

### ¿Por qué es accionable?

| Perspectiva | Valor |
|---|---|
| **Para equipos** | Optimizar la estrategia de pit stops y selección de circuitos según el perfil del piloto |
| **Para analistas** | Cuantificar el peso real de la posición de salida vs. la estrategia en el resultado final |
| **Para contexto histórico** | Identificar qué eras fueron dominadas por el constructor vs. por el talento del piloto |

---

## 📂 Estructura del Repositorio

```
proyecto-final/
├── README.md                        ← problema, modelo, cómo ejecutar, hallazgos
├── datasets/                        ← datos crudos (link de descarga Kaggle)
├── scripts/
│   ├── 01_schema_ddl.sql            ← creación del modelo dimensional
│   └── etl_pipeline.py              ← script ETL completo
├── dashboard/                       ← archivo del dashboard
└── docs/
    └── diagrama_modelo.png          ← diagrama del esquema estrella
```

---

## 📊 Dataset — Ergast F1 Database (1950–2024)

**Fuente:** [Kaggle — Formula 1 World Championship (1950–2024)](https://www.kaggle.com/datasets/rohanrao/formula-1-world-championship-1950-2020) · Dominio público

| Atributo | Detalle |
|---|---|
| **Archivos** | 14 archivos CSV interconectados con claves relacionales consistentes |
| **Volumen total** | ~590,000+ filas distribuidas entre tablas |
| **Cobertura** | 74 temporadas · ~1,100 Grandes Premios · 857 pilotos · 210 circuitos |
| **Actualización** | Temporada 2024 |

### Tablas principales

| Archivo | Filas aprox. | Descripción |
|---|---|---|
| `results.csv` | ~26,000 | Posición de salida, posición final, puntos, vueltas y status por piloto/carrera |
| `races.csv` | ~1,100 | Fecha, circuito, temporada y nombre del Gran Premio |
| `pit_stops.csv` | ~10,000+ | Duración, vuelta y posición al momento de cada parada |
| `lap_times.csv` | ~540,000 | Tiempo de vuelta por piloto y vuelta (desde 1996) |
| `drivers.csv` | 857 | Nombre, nacionalidad, fecha de nacimiento, código de piloto |
| `constructors.csv` | 211 | Nombre y nacionalidad del constructor |
| `circuits.csv` | 77 | Nombre, país y coordenadas geográficas |
| `qualifying.csv` | ~10,000 | Tiempos Q1/Q2/Q3 y posición de clasificación |

---

## 🗂️ Modelo Dimensional

### Esquema estrella

![Diagrama del modelo dimensional](docs/diagrama_modelo.png)

### Grano declarado

> **Un registro por piloto por carrera.**

Cada fila en `fact_resultado_carrera` representa el resultado de un piloto específico en una carrera específica. Esto permite analizar tanto el rendimiento individual como agregaciones por equipo, circuito y temporada sin pérdida de granularidad.

### Tabla de hechos — `fact_resultado_carrera`

| Columna | Tipo | Descripción |
|---|---|---|
| `piloto_sk` | INT FK | Surrogate key → dim_piloto |
| `constructor_sk` | INT FK | Surrogate key → dim_constructor |
| `circuito_sk` | INT FK | Surrogate key → dim_circuito |
| `tiempo_sk` | INT FK | Surrogate key → dim_tiempo |
| `estado_sk` | INT FK | Surrogate key → dim_estado |
| `posicion_salida` | INT | Grid position de salida |
| `posicion_final` | INT | Posición oficial de llegada (NULL si abandono) |
| `puntos` | NUMERIC | Puntos otorgados según el sistema de la era |
| `vueltas_completadas` | INT | Vueltas completadas en carrera |
| `num_pitstops` | INT | Conteo de paradas (calculado en ETL) |
| `tiempo_total_ms` | BIGINT | Tiempo total de carrera en milisegundos |
| `delta_posicion` | INT | `posicion_salida - posicion_final` (positivo = ganó posiciones) |
| `es_abandono` | BOOLEAN | Flag derivado del `status_id` |

**Clave primaria:** `(piloto_sk, tiempo_sk)` — garantiza unicidad al nivel del grano.

### Dimensiones

| Dimensión | Filas aprox. | SCD | Atributos clave |
|---|---|---|---|
| `dim_piloto` | 857 | Tipo 1 | nombre_completo, nacionalidad, fecha_nacimiento, codigo_piloto |
| `dim_constructor` | 211 | Tipo 1 | nombre, nacionalidad, referencia, era_f1 |
| `dim_circuito` | 77 | Tipo 1 | nombre, pais, localidad, latitud, longitud |
| `dim_tiempo` | ~1,100 | Tipo 1 | fecha, anio, temporada, numero_ronda, era_f1 |
| `dim_estado` | ~140 | Tipo 1 | categoria, descripcion |

### Decisiones de diseño

**`dim_piloto`** — Se desnormalizaron `nombre` y `apellido` en un solo campo `nombre_completo` para simplificar consultas. Se conserva `driver_id` como natural key para joins con fuentes externas. `fecha_nacimiento` incluida para análisis age-performance.

**`dim_constructor`** — Se agregó el atributo calculado `era_f1` (ej. "Era turbo 1977–88", "Era híbrida 2014+") para facilitar análisis de dominancia por período sin requerir CTEs complejos en cada consulta.

**`dim_circuito`** — Colapsa `circuits.csv` y metadata de `races.csv` en una sola dimensión. Incluye coordenadas geográficas (`latitud`, `longitud`) para habilitar mapas en el dashboard. El campo `pais` desnormalizado permite filtros rápidos sin JOIN adicional.

**`dim_tiempo`** — Grano de fecha de carrera (no calendario estándar diario), porque F1 tiene un calendario irregular. Incluye `numero_ronda` para análisis de momentum dentro de temporada y `era_f1` para filtros de largo plazo.

**`dim_estado`** — Mapea los 140+ códigos de `status` del dataset a 4 categorías analíticas: `Finalizado`, `Abandono mecánico`, `Accidente`, `Descalificado`. Esta desnormalización permite responder "¿qué % de abandonos son mecánicos vs. accidentes?" sin lógica compleja en SQL.

**Surrogate keys** — Todas las dimensiones usan surrogate keys (`_sk`) generadas con `ROW_NUMBER()` en el ETL, desacopladas de los IDs originales de Ergast. Las natural keys (`_id NK`) se conservan para auditoría.

---

## ☁️ Infraestructura AWS — Aurora PostgreSQL

### Configuración del cluster

| Parámetro | Valor |
|---|---|
| **Motor** | Aurora PostgreSQL 15.x |
| **Tipo de instancia** | `db.t3.medium` (desarrollo) |
| **Región** | `us-east-1` |
| **Puerto** | `5432` |
| **Schema DW** | `f1_dw` (separado del esquema `public`) |
| **Base de datos** | `f1_analytics` |

> El esquema `f1_dw` mantiene el Data Warehouse aislado del esquema `public` (OLTP), siguiendo buenas prácticas de separación de ambientes.

### Variables de entorno

Crea un archivo `.env` en la raíz del repositorio con las siguientes variables. **Nunca subas este archivo a GitHub** (ya está en `.gitignore`).

```bash
# .env — credenciales Aurora PostgreSQL
DB_HOST=<aurora-cluster-endpoint>.rds.amazonaws.com
DB_PORT=5432
DB_NAME=f1_analytics
DB_USER=<usuario>
DB_PASSWORD=<password>
DB_SCHEMA=f1_dw
```

### Pasos de configuración

**1. Crear el cluster Aurora en AWS Console**

```
RDS → Create database → Aurora (PostgreSQL) → db.t3.medium
Habilitar: Public access = Yes (solo para desarrollo desde Colab)
VPC Security Group: permitir inbound TCP 5432 desde tu IP
```

**2. Conectarse y crear la base de datos**

```bash
psql -h <aurora-endpoint> -U <usuario> -d postgres
```

```sql
CREATE DATABASE f1_analytics;
```

**3. Cargar el esquema dimensional**

```bash
psql -h <aurora-endpoint> -U <usuario> -d f1_analytics -f scripts/01_schema_ddl.sql
```

**4. Verificar que el esquema se creó correctamente**

```sql
SET search_path TO f1_dw;

SELECT table_name, obj_description(
    (quote_ident(table_schema)||'.'||quote_ident(table_name))::regclass, 'pg_class'
) AS descripcion
FROM information_schema.tables
WHERE table_schema = 'f1_dw'
ORDER BY table_name;
```

Deberías ver las 6 tablas: `dim_circuito`, `dim_constructor`, `dim_estado`, `dim_piloto`, `dim_tiempo`, `fact_resultado_carrera`.

### Buenas prácticas aplicadas

- Schema `f1_dw` separado del esquema `public` para aislar el DW
- Naming consistente: prefijos `dim_` y `fact_`, sufijos `_sk` (surrogate key), `_id` (natural key)
- `COMMENT ON TABLE/COLUMN` en cada objeto para documentación interna
- Índices en todas las FKs de la fact table y en columnas de filtro frecuente (`temporada`, `era_f1`, `es_abandono`)
- Índice parcial en `es_abandono = TRUE` para optimizar consultas de análisis de retiros
- Credenciales externalizadas en `.env`, nunca hardcodeadas en el código

## ⚙️ Cómo Ejecutar el Proyecto

### Pre-requisitos

```bash
pip install pandas sqlalchemy psycopg2-binary python-dotenv
```

### 1. Configurar variables de entorno

```bash
cp .env.example .env
# Editar .env con el endpoint de Aurora y credenciales
```

### 2. Cargar el esquema dimensional en Aurora

```bash
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -f scripts/01_schema_ddl.sql
```

### 3. Ejecutar el pipeline ETL

```bash
python scripts/etl_pipeline.py
```

---

## 🔍 Hallazgos

> _Se completará al finalizar el dashboard._

---

## 🛠️ Stack Tecnológico

| Capa | Tecnología |
|---|---|
| **Almacenamiento** | AWS Aurora PostgreSQL |
| **ETL** | Python · pandas · SQLAlchemy |
| **SQL avanzado** | Window functions · CTE · PERCENTILE_CONT · Stored procedures |
| **Dashboard** | Power BI / Streamlit |
| **Entorno de desarrollo** | Google Colab · GitHub |

---

## 👤 Autor

Proyecto final — Módulo 4: Inteligencia de Negocios y SQL Avanzado
