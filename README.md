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

> _Se completará en el Criterio 2._

El diagrama del esquema estrella se encuentra en [`docs/diagrama_modelo.png`](docs/diagrama_modelo.png).

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
