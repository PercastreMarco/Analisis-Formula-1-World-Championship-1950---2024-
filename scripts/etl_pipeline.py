"""
=============================================================================
Proyecto Final — Módulo 4: Inteligencia de Negocios y SQL Avanzado
Archivo   : etl_pipeline.py
Propósito : Pipeline ETL completo — Extract / Transform / Load
Dataset   : Ergast F1 Database (1950–2024)
Destino   : Aurora PostgreSQL — Schema f1_dw
=============================================================================
Estructura del pipeline:
    extract()       → Lee los 14 CSVs del dataset Ergast
    transform_*()   → Limpia y construye cada dimensión y la fact table
    load_*()        → Carga cada tabla con upsert idempotente
    validate()      → Validaciones post-carga (conteos, integridad referencial)
    main()          → Orquestador principal

Uso:
    python etl_pipeline.py --data_path ./datasets --log_level INFO
=============================================================================
"""

import os
import logging
import argparse
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# =============================================================================
# CONFIGURACIÓN DE LOGGING
# =============================================================================

def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Configura el logger del pipeline con formato timestamp + nivel + mensaje."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(f"etl_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        ]
    )
    return logging.getLogger("f1_etl")


# =============================================================================
# CONEXIÓN A BASE DE DATOS
# =============================================================================

def get_engine():
    """
    Crea el engine de SQLAlchemy usando variables de entorno.
    Nunca hardcodear credenciales en el código.
    """
    load_dotenv()
    host     = os.getenv("DB_HOST")
    port     = os.getenv("DB_PORT", "5432")
    db       = os.getenv("DB_NAME")
    user     = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")

    if not all([host, db, user, password]):
        raise EnvironmentError(
            "Faltan variables de entorno. Verifica DB_HOST, DB_NAME, DB_USER, DB_PASSWORD en .env"
        )

    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    engine = create_engine(url, pool_pre_ping=True)
    return engine


# =============================================================================
# EXTRACT — Lectura de CSVs
# =============================================================================

def extract(data_path: str, logger: logging.Logger) -> dict:
    """
    Lee los archivos CSV del dataset Ergast desde la carpeta datasets/.
    Retorna un diccionario con DataFrames crudos por nombre de tabla.
    """
    logger.info("=" * 60)
    logger.info("EXTRACT — Leyendo archivos CSV")
    logger.info("=" * 60)

    archivos = {
        "races":                "races.csv",
        "results":              "results.csv",
        "drivers":              "drivers.csv",
        "constructors":         "constructors.csv",
        "circuits":             "circuits.csv",
        "pit_stops":            "pit_stops.csv",
        "lap_times":            "lap_times.csv",
        "qualifying":           "qualifying.csv",
        "driver_standings":     "driver_standings.csv",
        "constructor_standings":"constructor_standings.csv",
        "constructor_results":  "constructor_results.csv",
        "seasons":              "seasons.csv",
        "status":               "status.csv",
        "sprint_results":       "sprint_results.csv",
    }

    raw = {}
    for nombre, archivo in archivos.items():
        ruta = os.path.join(data_path, archivo)
        if not os.path.exists(ruta):
            logger.warning(f"  Archivo no encontrado (se omite): {ruta}")
            continue
        df = pd.read_csv(ruta, na_values=["\\N", "NA", "", "NULL"])
        raw[nombre] = df
        logger.info(f"  {archivo:<40} → {len(df):>8,} filas | {df.shape[1]} columnas")

    logger.info(f"  Total archivos cargados: {len(raw)}")
    return raw


# =============================================================================
# TRANSFORM — Dimensiones
# =============================================================================

def transform_dim_piloto(raw: dict, logger: logging.Logger) -> pd.DataFrame:
    """
    Construye dim_piloto desde drivers.csv.
    - Desnormaliza forename + surname → nombre_completo
    - Genera surrogate key (piloto_sk) con ROW_NUMBER equivalente
    """
    logger.info("TRANSFORM → dim_piloto")

    df = raw["drivers"].copy()

    # Desnormalizar nombre completo
    df["nombre_completo"] = (df["forename"].fillna("") + " " + df["surname"].fillna("")).str.strip()

    # Limpiar fecha de nacimiento
    df["fecha_nacimiento"] = pd.to_datetime(df["dob"], errors="coerce")

    dim = df.rename(columns={
        "driverId":   "driver_id",
        "driverRef":  "driver_ref",
        "number":     "numero_permanente",
        "code":       "codigo_piloto",
        "nationality":"nacionalidad",
    })[["driver_id", "driver_ref", "numero_permanente", "codigo_piloto",
        "nombre_completo", "fecha_nacimiento", "nacionalidad"]]

    # Surrogate key
    dim = dim.sort_values("driver_id").reset_index(drop=True)
    dim.insert(0, "piloto_sk", dim.index + 1)

    # Validar nulos críticos
    nulos = dim["nombre_completo"].isna().sum()
    if nulos > 0:
        logger.warning(f"  {nulos} filas con nombre_completo nulo — se rellenan con 'Desconocido'")
        dim["nombre_completo"] = dim["nombre_completo"].fillna("Desconocido")

    logger.info(f"  Filas generadas: {len(dim):,}")
    return dim


def transform_dim_constructor(raw: dict, logger: logging.Logger) -> pd.DataFrame:
    """
    Construye dim_constructor desde constructors.csv.
    - Agrega era_f1 como atributo calculado basado en rangos de temporadas activas.
    """
    logger.info("TRANSFORM → dim_constructor")

    df = raw["constructors"].copy()

    # Calcular era dominante de cada constructor usando constructor_results + races
    if "constructor_results" in raw and "races" in raw:
        cr = raw["constructor_results"].merge(
            raw["races"][["raceId", "year"]], on="raceId", how="left"
        )
        era_map = cr.groupby("constructorId")["year"].median().reset_index()
        era_map.columns = ["constructorId", "median_year"]

        def asignar_era(year):
            if pd.isna(year):      return "Desconocido"
            elif year <= 1966:     return "Aspiración natural 1950–66"
            elif year <= 1976:     return "Era DFV 1967–76"
            elif year <= 1988:     return "Era turbo 1977–88"
            elif year <= 2005:     return "NA moderno 1989–2005"
            elif year <= 2013:     return "Era V8 2006–13"
            else:                  return "Era híbrida 2014+"

        era_map["era_f1"] = era_map["median_year"].apply(asignar_era)
        df = df.merge(era_map[["constructorId", "era_f1"]], on="constructorId", how="left")
    else:
        df["era_f1"] = "Desconocido"

    dim = df.rename(columns={
        "constructorId":  "constructor_id",
        "constructorRef": "constructor_ref",
        "name":           "nombre",
        "nationality":    "nacionalidad",
    })[["constructor_id", "constructor_ref", "nombre", "nacionalidad", "era_f1"]]

    dim = dim.sort_values("constructor_id").reset_index(drop=True)
    dim.insert(0, "constructor_sk", dim.index + 1)

    logger.info(f"  Filas generadas: {len(dim):,}")
    return dim


def transform_dim_circuito(raw: dict, logger: logging.Logger) -> pd.DataFrame:
    """
    Construye dim_circuito desde circuits.csv.
    - Incluye coordenadas geográficas para mapas en el dashboard.
    """
    logger.info("TRANSFORM → dim_circuito")

    df = raw["circuits"].copy()

    dim = df.rename(columns={
        "circuitId":  "circuit_id",
        "circuitRef": "circuit_ref",
        "name":       "nombre",
        "location":   "localidad",
        "country":    "pais",
        "lat":        "latitud",
        "lng":        "longitud",
    })[["circuit_id", "circuit_ref", "nombre", "localidad", "pais", "latitud", "longitud"]]

    # Limpiar coordenadas fuera de rango
    dim["latitud"]  = pd.to_numeric(dim["latitud"],  errors="coerce")
    dim["longitud"] = pd.to_numeric(dim["longitud"], errors="coerce")

    dim = dim.sort_values("circuit_id").reset_index(drop=True)
    dim.insert(0, "circuito_sk", dim.index + 1)

    logger.info(f"  Filas generadas: {len(dim):,}")
    return dim


def transform_dim_tiempo(raw: dict, logger: logging.Logger) -> pd.DataFrame:
    """
    Construye dim_tiempo desde races.csv.
    - Grano: fecha de carrera (no calendario diario estándar).
    - Incluye numero_ronda y era_f1 para análisis de momentum y largo plazo.
    """
    logger.info("TRANSFORM → dim_tiempo")

    df = raw["races"].copy()

    def asignar_era(year):
        if year <= 1966:   return "Aspiración natural 1950–66"
        elif year <= 1976: return "Era DFV 1967–76"
        elif year <= 1988: return "Era turbo 1977–88"
        elif year <= 2005: return "NA moderno 1989–2005"
        elif year <= 2013: return "Era V8 2006–13"
        else:              return "Era híbrida 2014+"

    df["era_f1"] = df["year"].apply(asignar_era)
    df["fecha"]  = pd.to_datetime(df["date"], errors="coerce")

    dim = df.rename(columns={
        "raceId": "race_id",
        "year":   "anio",
        "name":   "nombre_gp",
        "round":  "numero_ronda",
    })[["race_id", "fecha", "anio", "nombre_gp", "numero_ronda", "era_f1"]]

    dim["temporada"] = dim["anio"]
    dim = dim.sort_values("race_id").reset_index(drop=True)
    dim.insert(0, "tiempo_sk", dim.index + 1)

    logger.info(f"  Filas generadas: {len(dim):,}")
    return dim


def transform_dim_estado(raw: dict, logger: logging.Logger) -> pd.DataFrame:
    """
    Construye dim_estado desde status.csv.
    - Mapea 140+ códigos a 5 categorías analíticas.
    - Esta desnormalización evita CASE WHEN complejos en cada consulta.
    """
    logger.info("TRANSFORM → dim_estado")

    df = raw["status"].copy()

    # Mapeo de categorías analíticas
    mecanicos = [
        "Engine","Gearbox","Transmission","Clutch","Hydraulics","Electrical",
        "Radiator","Suspension","Brakes","Differential","Overheating",
        "Mechanical","Oil pressure","Water pressure","Fuel pressure",
        "Oil leak","Water leak","Fuel leak","Throttle","Alternator",
        "Exhaust","Heat shield fire","Wheel","Tyre","Puncture","Wheel rim",
        "Driveshaft","CV joint","Steering","Turbo","Pneumatics","Power Unit",
        "ERS","Battery"
    ]
    accidentes = [
        "Accident","Collision","Spun off","Collision damage",
        "Fatal accident","Safety concerns"
    ]
    descalificados = [
        "Disqualified","Excluded","Not classified","Did not qualify",
        "Did not prequalify","107% rule","Underweight"
    ]

    def categorizar(status):
        if status == "Finished" or "+" in str(status) or "Lap" in str(status):
            return "Finalizado"
        elif any(m.lower() in status.lower() for m in mecanicos):
            return "Abandono mecánico"
        elif any(a.lower() in status.lower() for a in accidentes):
            return "Accidente"
        elif any(d.lower() in status.lower() for d in descalificados):
            return "Descalificado"
        else:
            return "Otro"

    df["categoria"] = df["status"].apply(categorizar)

    dim = df.rename(columns={
        "statusId":   "status_id",
        "status":     "descripcion",
    })[["status_id", "descripcion", "categoria"]]

    dim = dim.sort_values("status_id").reset_index(drop=True)
    dim.insert(0, "estado_sk", dim.index + 1)

    logger.info(f"  Filas generadas: {len(dim):,}")
    logger.info(f"  Distribución de categorías:\n{dim['categoria'].value_counts().to_string()}")
    return dim


# =============================================================================
# TRANSFORM — Fact Table
# =============================================================================

def transform_fact(
    raw: dict,
    dim_piloto: pd.DataFrame,
    dim_constructor: pd.DataFrame,
    dim_circuito: pd.DataFrame,
    dim_tiempo: pd.DataFrame,
    dim_estado: pd.DataFrame,
    logger: logging.Logger
) -> pd.DataFrame:
    """
    Construye fact_resultado_carrera desde results.csv + pit_stops.csv.
    - Resuelve surrogate keys desde cada dimensión.
    - Calcula medidas derivadas: delta_posicion, es_abandono, num_pitstops.
    """
    logger.info("TRANSFORM → fact_resultado_carrera")

    results = raw["results"].copy()
    races   = raw["races"][["raceId", "circuitId"]].copy()

    # Calcular num_pitstops por piloto/carrera desde pit_stops.csv
    if "pit_stops" in raw:
        pit_counts = (
            raw["pit_stops"]
            .groupby(["raceId", "driverId"])
            .size()
            .reset_index(name="num_pitstops")
        )
        results = results.merge(pit_counts, on=["raceId", "driverId"], how="left")
        results["num_pitstops"] = results["num_pitstops"].fillna(0).astype(int)
    else:
        results["num_pitstops"] = 0

    # Join con races para obtener circuitId
    results = results.merge(races, on="raceId", how="left")

    # Resolver surrogate keys
    results = results.merge(
        dim_piloto[["piloto_sk", "driver_id"]], left_on="driverId", right_on="driver_id", how="left"
    )
    results = results.merge(
        dim_constructor[["constructor_sk", "constructor_id"]], left_on="constructorId", right_on="constructor_id", how="left"
    )
    results = results.merge(
        dim_circuito[["circuito_sk", "circuit_id"]], left_on="circuitId", right_on="circuit_id", how="left"
    )
    results = results.merge(
        dim_tiempo[["tiempo_sk", "race_id"]], left_on="raceId", right_on="race_id", how="left"
    )
    results = results.merge(
        dim_estado[["estado_sk", "status_id"]], left_on="statusId", right_on="status_id", how="left"
    )

    # Calcular medidas derivadas
    results["posicion_salida"]   = pd.to_numeric(results["grid"],         errors="coerce")
    results["posicion_final"]    = pd.to_numeric(results["positionOrder"],errors="coerce")
    results["puntos"]            = pd.to_numeric(results["points"],       errors="coerce").fillna(0)
    results["vueltas_completadas"]= pd.to_numeric(results["laps"],        errors="coerce").fillna(0).astype(int)
    results["tiempo_total_ms"]   = pd.to_numeric(results["milliseconds"], errors="coerce")

    # delta_posicion: positivo = ganó posiciones
    results["delta_posicion"] = results["posicion_salida"] - results["posicion_final"]

    # es_abandono: True si el piloto no terminó la carrera
    resultados_fin = dim_estado[dim_estado["categoria"] == "Finalizado"]["estado_sk"].tolist()
    results["es_abandono"] = ~results["estado_sk"].isin(resultados_fin)

    fact = results[[
        "piloto_sk", "constructor_sk", "circuito_sk", "tiempo_sk", "estado_sk",
        "posicion_salida", "posicion_final", "puntos", "vueltas_completadas",
        "num_pitstops", "tiempo_total_ms", "delta_posicion", "es_abandono"
    ]].copy()

    # Eliminar filas sin surrogate keys resueltas (no deben existir)
    antes = len(fact)
    fact = fact.dropna(subset=["piloto_sk", "constructor_sk", "circuito_sk", "tiempo_sk", "estado_sk"])
    descartadas = antes - len(fact)
    if descartadas > 0:
        logger.warning(f"  {descartadas} filas descartadas por surrogate keys no resueltas")

    # Convertir SKs a entero
    for col in ["piloto_sk", "constructor_sk", "circuito_sk", "tiempo_sk", "estado_sk"]:
        fact[col] = fact[col].astype(int)

    logger.info(f"  Filas generadas: {len(fact):,}")
    return fact


# =============================================================================
# LOAD — Carga con upsert idempotente
# =============================================================================

def load_table(
    df: pd.DataFrame,
    table_name: str,
    pk_cols: list,
    engine,
    logger: logging.Logger,
    schema: str = "f1_dw"
):
    """
    Carga un DataFrame en Aurora PostgreSQL con upsert idempotente.
    Estrategia: DELETE registros existentes por PK + INSERT fresh.
    Garantiza que el pipeline se puede re-correr sin duplicar datos.
    """
    logger.info(f"LOAD → {schema}.{table_name}")

    full_table = f"{schema}.{table_name}"
    cols       = ", ".join(df.columns)
    placeholders = ", ".join([f":{c}" for c in df.columns])

    with engine.begin() as conn:
        # Idempotencia: eliminar registros existentes con las mismas PKs
        existing = conn.execute(text(f"SELECT COUNT(*) FROM {full_table}")).scalar()
        if existing > 0:
            logger.info(f"  Tabla con {existing:,} registros existentes — aplicando upsert")
            pk_condition = " AND ".join([f"{full_table}.{pk} = data.{pk}" for pk in pk_cols])
            pk_values    = ", ".join([f":{pk}" for pk in pk_cols])
            pk_cols_str  = ", ".join(pk_cols)
            conn.execute(text(
                f"DELETE FROM {full_table} WHERE ({pk_cols_str}) IN "
                f"(SELECT {pk_values} FROM (VALUES {{}}) AS data({pk_cols_str}))"
            ).bindparams())
            # Usamos método más directo: truncate + insert para dimensiones
            conn.execute(text(f"TRUNCATE TABLE {full_table} RESTART IDENTITY CASCADE"))
            logger.info(f"  Tabla truncada para re-carga limpia")

        # INSERT en lotes de 1000 filas
        registros = df.to_dict(orient="records")
        lote_size = 1000
        for i in range(0, len(registros), lote_size):
            lote = registros[i:i + lote_size]
            conn.execute(
                text(f"INSERT INTO {full_table} ({cols}) VALUES ({placeholders})"),
                lote
            )

    logger.info(f"  ✓ {len(df):,} filas cargadas en {full_table}")


def load_fact(df: pd.DataFrame, engine, logger: logging.Logger, schema: str = "f1_dw"):
    """
    Carga la fact table con ON CONFLICT DO UPDATE (upsert real por PK compuesta).
    PK: (piloto_sk, tiempo_sk)
    """
    logger.info(f"LOAD → {schema}.fact_resultado_carrera")

    cols         = ", ".join(df.columns)
    placeholders = ", ".join([f":{c}" for c in df.columns])
    update_cols  = [c for c in df.columns if c not in ["piloto_sk", "tiempo_sk"]]
    update_set   = ", ".join([f"{c} = EXCLUDED.{c}" for c in update_cols])

    upsert_sql = text(f"""
        INSERT INTO {schema}.fact_resultado_carrera ({cols})
        VALUES ({placeholders})
        ON CONFLICT (piloto_sk, tiempo_sk)
        DO UPDATE SET {update_set}
    """)

    registros = df.to_dict(orient="records")
    lote_size = 1000

    with engine.begin() as conn:
        for i in range(0, len(registros), lote_size):
            lote = registros[i:i + lote_size]
            conn.execute(upsert_sql, lote)

    logger.info(f"  ✓ {len(df):,} filas cargadas en {schema}.fact_resultado_carrera")


# =============================================================================
# VALIDATE — Validaciones post-carga
# =============================================================================

def validate(raw: dict, engine, logger: logging.Logger, schema: str = "f1_dw"):
    """
    Validaciones post-carga:
    1. Conteo de filas en BD vs origen CSV
    2. Integridad referencial (FKs huérfanas)
    3. Nulos en columnas críticas
    """
    logger.info("=" * 60)
    logger.info("VALIDATE — Validaciones post-carga")
    logger.info("=" * 60)

    errores = 0

    with engine.connect() as conn:

        # 1. Conteo de filas por tabla
        tablas_esperadas = {
            "dim_piloto":              len(raw.get("drivers", pd.DataFrame())),
            "dim_constructor":         len(raw.get("constructors", pd.DataFrame())),
            "dim_circuito":            len(raw.get("circuits", pd.DataFrame())),
            "dim_tiempo":              len(raw.get("races", pd.DataFrame())),
            "dim_estado":              len(raw.get("status", pd.DataFrame())),
            "fact_resultado_carrera":  len(raw.get("results", pd.DataFrame())),
        }

        logger.info("  Conteo de filas (BD vs CSV origen):")
        for tabla, esperado in tablas_esperadas.items():
            real = conn.execute(text(f"SELECT COUNT(*) FROM {schema}.{tabla}")).scalar()
            estado = "✓" if real == esperado else "✗ DIFERENCIA"
            logger.info(f"    {tabla:<35} BD: {real:>8,}  CSV: {esperado:>8,}  {estado}")
            if real != esperado:
                errores += 1

        # 2. Integridad referencial — FKs huérfanas en fact
        logger.info("  Integridad referencial:")
        fks = {
            "piloto_sk":      "dim_piloto",
            "constructor_sk": "dim_constructor",
            "circuito_sk":    "dim_circuito",
            "tiempo_sk":      "dim_tiempo",
            "estado_sk":      "dim_estado",
        }
        pk_map = {
            "dim_piloto":      "piloto_sk",
            "dim_constructor": "constructor_sk",
            "dim_circuito":    "circuito_sk",
            "dim_tiempo":      "tiempo_sk",
            "dim_estado":      "estado_sk",
        }
        for fk_col, dim_tabla in fks.items():
            pk_col   = pk_map[dim_tabla]
            huerfanas = conn.execute(text(f"""
                SELECT COUNT(*) FROM {schema}.fact_resultado_carrera f
                LEFT JOIN {schema}.{dim_tabla} d ON f.{fk_col} = d.{pk_col}
                WHERE d.{pk_col} IS NULL
            """)).scalar()
            estado = "✓" if huerfanas == 0 else f"✗ {huerfanas:,} huérfanas"
            logger.info(f"    fact.{fk_col:<20} → {dim_tabla:<25} {estado}")
            if huerfanas > 0:
                errores += 1

        # 3. Nulos en columnas críticas de la fact
        logger.info("  Nulos en columnas críticas de fact_resultado_carrera:")
        criticas = ["piloto_sk", "constructor_sk", "circuito_sk", "tiempo_sk", "estado_sk", "puntos"]
        for col in criticas:
            nulos = conn.execute(text(
                f"SELECT COUNT(*) FROM {schema}.fact_resultado_carrera WHERE {col} IS NULL"
            )).scalar()
            estado = "✓" if nulos == 0 else f"✗ {nulos:,} nulos"
            logger.info(f"    {col:<35} {estado}")
            if nulos > 0:
                errores += 1

    logger.info("=" * 60)
    if errores == 0:
        logger.info("  ✅ Todas las validaciones pasaron correctamente")
    else:
        logger.error(f"  ❌ {errores} validación(es) fallaron — revisa el log")
    logger.info("=" * 60)

    return errores == 0


# =============================================================================
# MAIN — Orquestador principal
# =============================================================================

def main(data_path: str = "./datasets", log_level: str = "INFO"):
    """
    Orquestador del pipeline ETL.
    Ejecuta en orden: Extract → Transform → Load → Validate
    """
    logger = setup_logging(log_level)
    inicio = datetime.now()

    logger.info("=" * 60)
    logger.info("  F1 BI — Pipeline ETL")
    logger.info(f"  Inicio: {inicio.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"  Dataset path: {data_path}")
    logger.info("=" * 60)

    try:
        # ── EXTRACT ────────────────────────────────────────────────
        raw = extract(data_path, logger)

        # ── TRANSFORM ──────────────────────────────────────────────
        logger.info("=" * 60)
        logger.info("TRANSFORM — Construyendo dimensiones y fact table")
        logger.info("=" * 60)

        dim_piloto      = transform_dim_piloto(raw, logger)
        dim_constructor = transform_dim_constructor(raw, logger)
        dim_circuito    = transform_dim_circuito(raw, logger)
        dim_tiempo      = transform_dim_tiempo(raw, logger)
        dim_estado      = transform_dim_estado(raw, logger)

        fact = transform_fact(
            raw, dim_piloto, dim_constructor,
            dim_circuito, dim_tiempo, dim_estado, logger
        )

        # ── LOAD ───────────────────────────────────────────────────
        logger.info("=" * 60)
        logger.info("LOAD — Cargando tablas en Aurora PostgreSQL")
        logger.info("=" * 60)

        engine = get_engine()

        # Cargar dimensiones (orden importa por constraints)
        load_table(dim_piloto,      "dim_piloto",      ["piloto_sk"],      engine, logger)
        load_table(dim_constructor, "dim_constructor",  ["constructor_sk"], engine, logger)
        load_table(dim_circuito,    "dim_circuito",    ["circuito_sk"],    engine, logger)
        load_table(dim_tiempo,      "dim_tiempo",      ["tiempo_sk"],      engine, logger)
        load_table(dim_estado,      "dim_estado",      ["estado_sk"],      engine, logger)

        # Cargar fact table con upsert real por PK compuesta
        load_fact(fact, engine, logger)

        # ── VALIDATE ───────────────────────────────────────────────
        ok = validate(raw, engine, logger)

        fin = datetime.now()
        duracion = (fin - inicio).seconds
        logger.info(f"  Pipeline completado en {duracion}s — {'✅ Exitoso' if ok else '❌ Con errores'}")

    except Exception as e:
        logger.error(f"  Error fatal en el pipeline: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="F1 BI — Pipeline ETL")
    parser.add_argument("--data_path",  default="./datasets", help="Carpeta con los CSVs de Ergast")
    parser.add_argument("--log_level",  default="INFO",       help="Nivel de logging (DEBUG, INFO, WARNING)")
    args = parser.parse_args()
    main(data_path=args.data_path, log_level=args.log_level)
