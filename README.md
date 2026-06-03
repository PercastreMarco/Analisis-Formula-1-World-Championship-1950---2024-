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

## ⚙️ Cómo Ejecutar el Proyecto

> _Se completará conforme avancen los criterios._

### Pre-requisitos

```bash
pip install pandas sqlalchemy psycopg2-binary python-dotenv
```

### 1. Configurar variables de entorno

```bash
cp .env.example .env
# Editar .env con las credenciales de Aurora PostgreSQL
```

### 2. Crear el esquema dimensional en AWS Aurora

```bash
psql -h <host> -U <user> -d <db> -f scripts/01_schema_ddl.sql
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
