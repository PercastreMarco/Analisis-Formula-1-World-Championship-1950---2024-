"""
=============================================================================
F1 BI — Dashboard Streamlit
Proyecto Final · Módulo 4: Inteligencia de Negocios y SQL Avanzado
=============================================================================
Visualizaciones:
  1. Campeonato de Constructores — evolución de puntos por temporada
  2. Estrategia vs Resultado — impacto de pit stops y posición de salida
  3. Dominancia por Era — tasa de victoria y abandono por constructor/era
  4. Circuitos — posición mediana de ganadores (PERCENTILE_CONT)
  5. Edad de Ganadores — evolución histórica por temporada
=============================================================================
"""

import os
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sqlalchemy import create_engine, text

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN DE PÁGINA
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="F1 Analytics · BI Dashboard",
    page_icon="🏎️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# PALETA Y ESTILOS F1
# ─────────────────────────────────────────────────────────────────────────────
F1_RED    = "#E8231A"
F1_BLACK  = "#1A1A1A"
F1_SILVER = "#C0C0C0"
F1_WHITE  = "#F5F4F0"
F1_GOLD   = "#F5A623"

ERA_COLORS = {
    "Aspiracion natural 1950-66": "#6B8CFF",
    "Era DFV 1967-76":            "#4CAF82",
    "Era turbo 1977-88":          "#F5A623",
    "NA moderno 1989-2005":       "#E8231A",
    "Era V8 2006-13":             "#9C27B0",
    "Era hibrida 2014+":          "#00BCD4",
}

TEAM_COLORS = {
    "Red Bull":    "#1E3A8A", "Ferrari":     "#E8231A",
    "Mercedes":    "#00D2BE", "McLaren":     "#FF8000",
    "Aston Martin":"#006F62", "Alpine":      "#0090FF",
    "Williams":    "#005AFF", "AlphaTauri":  "#2B4562",
    "Alfa Romeo":  "#900000", "Haas F1 Team":"#FFFFFF",
}

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;600;700;900&family=Barlow:wght@400;500;600&display=swap');

  html, body, [class*="css"] {
      font-family: 'Barlow', sans-serif;
      background-color: #111111;
      color: #F5F4F0;
  }
  .main { background-color: #111111; }
  .block-container { padding: 1.5rem 2rem; max-width: 1400px; }

  /* Header principal */
  .f1-header {
      display: flex; align-items: center; gap: 16px;
      border-bottom: 3px solid #E8231A;
      padding-bottom: 1rem; margin-bottom: 1.5rem;
  }
  .f1-flag {
      width: 10px; height: 60px;
      background: repeating-linear-gradient(to bottom,
          #000 0px,#000 8px,#fff 8px,#fff 16px);
      border-radius: 1px; flex-shrink: 0;
  }
  .f1-title {
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 2.4rem; font-weight: 900;
      letter-spacing: 0.03em; line-height: 1;
      color: #F5F4F0;
  }
  .f1-title span { color: #E8231A; }
  .f1-subtitle {
      font-size: 0.78rem; font-weight: 600;
      letter-spacing: 0.1em; text-transform: uppercase;
      color: #888; margin-top: 4px;
  }

  /* KPI cards */
  .kpi-grid { display: flex; gap: 12px; margin-bottom: 1.5rem; flex-wrap: wrap; }
  .kpi-card {
      background: #1E1E1E; border: 1px solid #2C2C2C;
      border-top: 3px solid #E8231A; border-radius: 6px;
      padding: 1rem 1.25rem; flex: 1; min-width: 140px;
  }
  .kpi-value {
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 2rem; font-weight: 700; color: #F5F4F0;
      line-height: 1;
  }
  .kpi-label { font-size: 0.72rem; color: #888; margin-top: 4px;
      font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; }

  /* Section headers */
  .section-title {
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 1.1rem; font-weight: 700;
      letter-spacing: 0.06em; text-transform: uppercase;
      color: #F5F4F0; border-left: 4px solid #E8231A;
      padding-left: 10px; margin: 1.5rem 0 0.75rem;
  }

  /* Sidebar */
  .css-1d391kg, [data-testid="stSidebar"] {
      background: #1A1A1A;
      border-right: 1px solid #2C2C2C;
  }
  [data-testid="stSidebar"] .stSelectbox label,
  [data-testid="stSidebar"] .stMultiSelect label,
  [data-testid="stSidebar"] .stSlider label { color: #C0C0C0; font-size: 0.8rem; }

  /* Charts background */
  .js-plotly-plot { border-radius: 6px; }

  /* Footer */
  .f1-footer {
      text-align: center; font-size: 0.7rem; color: #555;
      border-top: 1px solid #2C2C2C; padding-top: 1rem; margin-top: 2rem;
      letter-spacing: 0.05em; text-transform: uppercase;
  }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# CONEXIÓN A AURORA
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_resource
def get_engine():
    host     = os.getenv("F1_HOST")
    password = os.getenv("F1_DATA")
    user     = os.getenv("F1_USER", "postgres")
    return create_engine(
        f"postgresql+psycopg2://{user}:{password}@{host}:5432/postgres",
        pool_pre_ping=True
    )

engine = get_engine()

# ─────────────────────────────────────────────────────────────────────────────
# CARGA DE DATOS CON CACHÉ
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_campeonato(temporada: int) -> pd.DataFrame:
    sql = """
    WITH puntos_por_ronda AS (
        SELECT t.temporada, t.numero_ronda, t.nombre_gp,
               p.nombre_completo AS piloto, c.nombre AS constructor, f.puntos
        FROM f1_dw.fact_resultado_carrera f
        JOIN f1_dw.dim_piloto      p ON f.piloto_sk      = p.piloto_sk
        JOIN f1_dw.dim_constructor c ON f.constructor_sk = c.constructor_sk
        JOIN f1_dw.dim_tiempo      t ON f.tiempo_sk      = t.tiempo_sk
        WHERE t.temporada = :temporada
    ),
    acumulado AS (
        SELECT temporada, numero_ronda, nombre_gp, piloto, constructor, puntos,
               SUM(puntos) OVER (
                   PARTITION BY temporada, piloto ORDER BY numero_ronda
                   ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
               ) AS puntos_acumulados,
               LAG(puntos, 1, 0) OVER (
                   PARTITION BY temporada, piloto ORDER BY numero_ronda
               ) AS puntos_ronda_anterior
        FROM puntos_por_ronda
    ),
    con_ranking AS (
        SELECT *, RANK() OVER (
            PARTITION BY temporada, numero_ronda ORDER BY puntos_acumulados DESC
        ) AS posicion_campeonato
        FROM acumulado
    )
    SELECT numero_ronda, nombre_gp, piloto, constructor,
           puntos AS puntos_ronda, puntos_acumulados, posicion_campeonato,
           puntos - puntos_ronda_anterior AS variacion
    FROM con_ranking
    WHERE posicion_campeonato <= 10
    ORDER BY numero_ronda, posicion_campeonato
    """
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params={"temporada": temporada})


@st.cache_data(ttl=3600)
def load_constructores_era() -> pd.DataFrame:
    sql = """
    WITH base AS (
        SELECT c.nombre AS constructor, c.era_f1,
               f.posicion_salida, f.posicion_final,
               f.delta_posicion, f.es_abandono, e.categoria
        FROM f1_dw.fact_resultado_carrera f
        JOIN f1_dw.dim_constructor c ON f.constructor_sk = c.constructor_sk
        JOIN f1_dw.dim_estado      e ON f.estado_sk      = e.estado_sk
        WHERE f.posicion_salida IS NOT NULL AND f.posicion_salida > 0
    ),
    metricas AS (
        SELECT constructor, era_f1, COUNT(*) AS entradas,
               ROUND(AVG(delta_posicion)::NUMERIC, 2) AS avg_delta,
               ROUND(SUM(CASE WHEN NOT es_abandono THEN 1 ELSE 0 END)::NUMERIC
                   / NULLIF(COUNT(*),0)*100,1) AS pct_finaliza,
               ROUND(SUM(CASE WHEN categoria='Abandono mecanico' THEN 1 ELSE 0 END)::NUMERIC
                   / NULLIF(COUNT(*),0)*100,1) AS pct_mecanico,
               SUM(CASE WHEN posicion_final=1 THEN 1 ELSE 0 END) AS victorias
        FROM base GROUP BY constructor, era_f1 HAVING COUNT(*) >= 20
    )
    SELECT *, RANK() OVER (PARTITION BY era_f1
        ORDER BY pct_finaliza DESC, avg_delta DESC) AS rank_era
    FROM metricas ORDER BY era_f1, rank_era
    """
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)


@st.cache_data(ttl=3600)
def load_circuitos() -> pd.DataFrame:
    sql = """
    WITH ganadores AS (
        SELECT ci.nombre AS circuito, ci.pais,
               ci.latitud, ci.longitud, f.posicion_salida
        FROM f1_dw.fact_resultado_carrera f
        JOIN f1_dw.dim_circuito ci ON f.circuito_sk = ci.circuito_sk
        WHERE f.posicion_final=1 AND f.posicion_salida IS NOT NULL
          AND f.posicion_salida > 0
    )
    SELECT circuito, pais, latitud, longitud,
           COUNT(*) AS total_ganadores,
           PERCENTILE_CONT(0.5)  WITHIN GROUP (ORDER BY posicion_salida) AS mediana_grid,
           PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY posicion_salida) AS p25_grid,
           PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY posicion_salida) AS p75_grid,
           ROUND(SUM(CASE WHEN posicion_salida=1 THEN 1 ELSE 0 END)::NUMERIC
               / NULLIF(COUNT(*),0)*100,1) AS pct_pole,
           MAX(posicion_salida) AS peor_grid
    FROM ganadores
    GROUP BY circuito, pais, latitud, longitud
    HAVING COUNT(*) >= 5
    ORDER BY mediana_grid ASC
    """
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)


@st.cache_data(ttl=3600)
def load_edad_ganadores() -> pd.DataFrame:
    sql = """
    WITH eg AS (
        SELECT t.temporada, t.era_f1,
               DATE_PART('year', AGE(t.fecha, p.fecha_nacimiento)) AS edad
        FROM f1_dw.fact_resultado_carrera f
        JOIN f1_dw.dim_piloto p ON f.piloto_sk = p.piloto_sk
        JOIN f1_dw.dim_tiempo t ON f.tiempo_sk  = t.tiempo_sk
        WHERE f.posicion_final=1
          AND p.fecha_nacimiento IS NOT NULL AND t.fecha IS NOT NULL
    ),
    agg AS (
        SELECT era_f1, temporada, COUNT(*) AS carreras,
               ROUND(AVG(edad)::NUMERIC,1) AS avg_edad,
               MIN(edad) AS edad_min, MAX(edad) AS edad_max,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY edad) AS mediana
        FROM eg GROUP BY era_f1, temporada
    )
    SELECT *, avg_edad - LAG(avg_edad) OVER (ORDER BY temporada) AS variacion
    FROM agg ORDER BY temporada
    """
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)


@st.cache_data(ttl=3600)
def load_pitstops_impacto() -> pd.DataFrame:
    sql = """
    SELECT
        f.num_pitstops,
        f.posicion_salida,
        f.posicion_final,
        f.delta_posicion,
        f.puntos,
        f.es_abandono,
        c.nombre  AS constructor,
        ci.nombre AS circuito,
        t.temporada,
        t.era_f1
    FROM f1_dw.fact_resultado_carrera f
    JOIN f1_dw.dim_constructor c  ON f.constructor_sk = c.constructor_sk
    JOIN f1_dw.dim_circuito    ci ON f.circuito_sk    = ci.circuito_sk
    JOIN f1_dw.dim_tiempo      t  ON f.tiempo_sk      = t.tiempo_sk
    WHERE f.num_pitstops > 0
      AND f.posicion_salida IS NOT NULL
      AND f.posicion_salida > 0
      AND t.temporada >= 1994
    """
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)


@st.cache_data(ttl=3600)
def load_kpis() -> dict:
    sql = """
    SELECT
        (SELECT COUNT(DISTINCT piloto_sk)       FROM f1_dw.fact_resultado_carrera) AS pilotos,
        (SELECT COUNT(DISTINCT constructor_sk)  FROM f1_dw.fact_resultado_carrera) AS constructores,
        (SELECT COUNT(DISTINCT tiempo_sk)       FROM f1_dw.fact_resultado_carrera) AS carreras,
        (SELECT COUNT(DISTINCT circuito_sk)     FROM f1_dw.fact_resultado_carrera) AS circuitos,
        (SELECT MIN(t.anio) FROM f1_dw.dim_tiempo t)                               AS anio_inicio,
        (SELECT MAX(t.anio) FROM f1_dw.dim_tiempo t)                               AS anio_fin
    """
    with engine.connect() as conn:
        row = conn.execute(text(sql)).fetchone()
        return dict(row._mapping)


# ─────────────────────────────────────────────────────────────────────────────
# PLOTLY THEME
# ─────────────────────────────────────────────────────────────────────────────
PLOTLY_LAYOUT = dict(
    paper_bgcolor="#1A1A1A",
    plot_bgcolor="#1A1A1A",
    font=dict(family="Barlow, sans-serif", color="#C0C0C0", size=12),
    title_font=dict(family="Barlow Condensed, sans-serif", size=16,
                    color="#F5F4F0"),
    legend=dict(bgcolor="#1E1E1E", bordercolor="#2C2C2C", borderwidth=1,
                font=dict(size=11)),
    xaxis=dict(gridcolor="#2C2C2C", linecolor="#333", tickfont=dict(size=11)),
    yaxis=dict(gridcolor="#2C2C2C", linecolor="#333", tickfont=dict(size=11)),
    margin=dict(l=40, r=20, t=50, b=40),
    hovermode="x unified",
)


# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="f1-header">
  <div class="f1-flag"></div>
  <div>
    <div class="f1-title">F1 <span>Analytics</span></div>
    <div class="f1-subtitle">
      Rendimiento de pilotos y estrategias de carrera · 1950–2024
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# KPIs
# ─────────────────────────────────────────────────────────────────────────────
kpis = load_kpis()
st.markdown(f"""
<div class="kpi-grid">
  <div class="kpi-card">
    <div class="kpi-value">{kpis['carreras']:,}</div>
    <div class="kpi-label">Carreras</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-value">{kpis['pilotos']:,}</div>
    <div class="kpi-label">Pilotos</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-value">{kpis['constructores']:,}</div>
    <div class="kpi-label">Constructores</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-value">{kpis['circuitos']:,}</div>
    <div class="kpi-label">Circuitos</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-value">{kpis['anio_inicio']}–{kpis['anio_fin']}</div>
    <div class="kpi-label">Cobertura</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR — Filtros globales
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="font-family:'Barlow Condensed',sans-serif;
                font-size:1.3rem;font-weight:700;color:#F5F4F0;
                border-bottom:2px solid #E8231A;padding-bottom:8px;
                margin-bottom:1rem;letter-spacing:0.05em;">
        🏎 FILTROS
    </div>
    """, unsafe_allow_html=True)

    temporada_sel = st.selectbox(
        "Temporada (campeonato)",
        options=list(range(2023, 1949, -1)),
        index=0
    )

    era_opciones = list(ERA_COLORS.keys())
    eras_sel = st.multiselect(
        "Eras técnicas",
        options=era_opciones,
        default=era_opciones,
    )

    top_n = st.slider("Top N pilotos (campeonato)", 3, 10, 5)

    st.markdown("---")
    st.markdown(
        "<div style='font-size:0.7rem;color:#555;letter-spacing:0.05em;"
        "text-transform:uppercase;'>Módulo 4 · BI y SQL Avanzado</div>",
        unsafe_allow_html=True
    )


# ─────────────────────────────────────────────────────────────────────────────
# VIZ 1 — CAMPEONATO: evolución de puntos por ronda (Window Functions)
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    '<div class="section-title">01 · Campeonato — Evolución de puntos por ronda</div>',
    unsafe_allow_html=True
)
st.caption(
    "SQL: Window Functions — SUM() OVER, LAG(), RANK() · "
    "¿Quién lideró el campeonato en cada ronda?"
)

df_camp = load_campeonato(temporada_sel)

if df_camp.empty:
    st.warning(f"Sin datos para la temporada {temporada_sel}.")
else:
    top_pilotos = (
        df_camp[df_camp["numero_ronda"] == df_camp["numero_ronda"].max()]
        .nsmallest(top_n, "posicion_campeonato")["piloto"].tolist()
    )
    df_top = df_camp[df_camp["piloto"].isin(top_pilotos)]

    col1, col2 = st.columns([2, 1])

    with col1:
        fig1 = px.line(
            df_top,
            x="numero_ronda", y="puntos_acumulados",
            color="piloto",
            markers=True,
            labels={
                "numero_ronda": "Ronda", "puntos_acumulados": "Puntos acumulados",
                "piloto": "Piloto"
            },
            title=f"Puntos acumulados — Temporada {temporada_sel}",
            color_discrete_sequence=px.colors.qualitative.Bold,
        )
        fig1.update_traces(line_width=2.5, marker_size=6)
        fig1.update_layout(**PLOTLY_LAYOUT)
        fig1.update_xaxes(title="Ronda")
        fig1.update_yaxes(title="Puntos acumulados")
        st.plotly_chart(fig1, use_container_width=True)

    with col2:
        # Tabla de posiciones al final de temporada
        ultima_ronda = df_camp["numero_ronda"].max()
        df_final = (
            df_camp[df_camp["numero_ronda"] == ultima_ronda]
            .sort_values("posicion_campeonato")
            [["posicion_campeonato", "piloto", "constructor", "puntos_acumulados"]]
            .rename(columns={
                "posicion_campeonato": "Pos",
                "piloto": "Piloto",
                "constructor": "Equipo",
                "puntos_acumulados": "Pts"
            })
            .head(10)
            .reset_index(drop=True)
        )
        st.markdown(
            f"<div style='font-size:0.8rem;color:#888;font-weight:600;"
            f"letter-spacing:0.06em;text-transform:uppercase;"
            f"margin-bottom:8px;'>Clasificación final ronda {ultima_ronda}</div>",
            unsafe_allow_html=True
        )
        st.dataframe(df_final, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# VIZ 2 — IMPACTO DE PIT STOPS Y POSICIÓN DE SALIDA
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    '<div class="section-title">02 · Estrategia — Pit stops y posición de salida</div>',
    unsafe_allow_html=True
)
st.caption(
    "¿Cuántas paradas y desde qué posición se gana? "
    "Filtrado por era en el sidebar."
)

df_pits = load_pitstops_impacto()
df_pits_f = df_pits[df_pits["era_f1"].isin(eras_sel)] if eras_sel else df_pits

col3, col4 = st.columns(2)

with col3:
    # Delta posición promedio por número de pit stops
    df_pits_agg = (
        df_pits_f.groupby("num_pitstops")
        .agg(
            avg_delta=("delta_posicion", "mean"),
            avg_pos_final=("posicion_final", "mean"),
            n=("puntos", "count")
        )
        .reset_index()
        .query("num_pitstops <= 5 and n >= 50")
    )
    fig2 = go.Figure()
    fig2.add_trace(go.Bar(
        x=df_pits_agg["num_pitstops"],
        y=df_pits_agg["avg_delta"].round(1),
        marker_color=[F1_RED if v > 0 else "#378ADD"
                      for v in df_pits_agg["avg_delta"]],
        text=df_pits_agg["avg_delta"].round(1),
        textposition="outside",
        name="Delta posición promedio",
    ))
    fig2.add_hline(y=0, line_dash="dash", line_color="#666", line_width=1)
    fig2.update_layout(
        **PLOTLY_LAYOUT,
        title="Posiciones ganadas (+) / perdidas (-) por N° de paradas",
        xaxis_title="Número de pit stops",
        yaxis_title="Delta posición promedio",
        showlegend=False,
    )
    st.plotly_chart(fig2, use_container_width=True)

with col4:
    # % victorias por posición de salida (grid 1-10)
    df_grid = (
        df_pits_f[df_pits_f["posicion_salida"] <= 10]
        .groupby("posicion_salida")
        .apply(lambda x: pd.Series({
            "pct_victoria": (x["posicion_final"] == 1).mean() * 100,
            "n": len(x)
        }))
        .reset_index()
        .query("n >= 30")
    )
    fig3 = go.Figure()
    fig3.add_trace(go.Bar(
        x=df_grid["posicion_salida"],
        y=df_grid["pct_victoria"].round(1),
        marker=dict(
            color=df_grid["pct_victoria"],
            colorscale=[[0, "#1E1E1E"], [0.5, "#F5A623"], [1, F1_RED]],
            showscale=False,
        ),
        text=df_grid["pct_victoria"].round(1).astype(str) + "%",
        textposition="outside",
    ))
    fig3.update_layout(
        **PLOTLY_LAYOUT,
        title="% de victorias según posición de salida (grid 1–10)",
        xaxis=dict(title="Posición de salida", tickvals=list(range(1, 11)),
                   gridcolor="#2C2C2C"),
        yaxis=dict(title="% victorias", ticksuffix="%", gridcolor="#2C2C2C"),
        showlegend=False,
    )
    st.plotly_chart(fig3, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# VIZ 3 — DOMINANCIA POR ERA (CTEs anidados)
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    '<div class="section-title">03 · Dominancia — Eficiencia de constructores por era</div>',
    unsafe_allow_html=True
)
st.caption(
    "SQL: CTEs anidados 3 niveles — base → métricas → ranking · "
    "Top 3 constructores más eficientes por era histórica"
)

df_era = load_constructores_era()
df_era_f = df_era[df_era["era_f1"].isin(eras_sel)] if eras_sel else df_era
df_era_top3 = df_era_f[df_era_f["rank_era"] <= 3]

col5, col6 = st.columns([3, 2])

with col5:
    fig4 = px.bar(
        df_era_top3,
        x="era_f1", y="victorias",
        color="constructor",
        barmode="group",
        title="Victorias por constructor — Top 3 de cada era",
        labels={"era_f1": "Era", "victorias": "Victorias", "constructor": "Constructor"},
        color_discrete_sequence=px.colors.qualitative.Bold,
    )
    fig4.update_layout(**PLOTLY_LAYOUT)
    fig4.update_xaxes(tickangle=-20)
    st.plotly_chart(fig4, use_container_width=True)

with col6:
    fig5 = px.scatter(
        df_era_top3,
        x="pct_mecanico",
        y="pct_finaliza",
        color="era_f1",
        size="victorias",
        hover_name="constructor",
        title="Fiabilidad vs Tasa de finalización",
        labels={
            "pct_mecanico": "% Abandono mecánico",
            "pct_finaliza": "% Finaliza carrera",
            "era_f1": "Era"
        },
        color_discrete_map={k: v for k, v in ERA_COLORS.items()},
    )
    fig5.update_layout(**PLOTLY_LAYOUT)
    st.plotly_chart(fig5, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# VIZ 4 — CIRCUITOS: PERCENTILE_CONT
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    '<div class="section-title">04 · Circuitos — Posición mediana de ganadores</div>',
    unsafe_allow_html=True
)
st.caption(
    "SQL: PERCENTILE_CONT(0.5) WITHIN GROUP · "
    "¿Desde qué posición se gana históricamente en cada pista?"
)

df_circ = load_circuitos()

col7, col8 = st.columns([1, 2])

with col7:
    top_n_circ = st.slider("Top N circuitos", 5, 30, 15, key="circ_slider")
    mostrar = st.radio(
        "Ordenar por",
        ["Más domina la pole", "Más abiertos a estrategia"],
        horizontal=False
    )

with col8:
    if mostrar == "Más domina la pole":
        df_plot = df_circ.nsmallest(top_n_circ, "mediana_grid")
        titulo = f"Top {top_n_circ} circuitos donde más importa la pole"
    else:
        df_plot = df_circ.nlargest(top_n_circ, "mediana_grid")
        titulo = f"Top {top_n_circ} circuitos más abiertos a la estrategia"

    fig6 = go.Figure()
    fig6.add_trace(go.Scatter(
        x=df_plot["p25_grid"], y=df_plot["circuito"],
        mode="markers", marker=dict(color="#2C2C2C", size=8),
        name="P25", showlegend=True,
    ))
    fig6.add_trace(go.Scatter(
        x=df_plot["p75_grid"], y=df_plot["circuito"],
        mode="markers", marker=dict(color="#2C2C2C", size=8),
        name="P75", showlegend=True,
    ))
    for _, row in df_plot.iterrows():
        fig6.add_shape(type="line",
            x0=row["p25_grid"], x1=row["p75_grid"],
            y0=row["circuito"],  y1=row["circuito"],
            line=dict(color="#444", width=3)
        )
    fig6.add_trace(go.Scatter(
        x=df_plot["mediana_grid"], y=df_plot["circuito"],
        mode="markers",
        marker=dict(color=F1_RED, size=12, symbol="diamond"),
        name="Mediana (P50)",
        text=df_plot["pct_pole"].astype(str) + "% desde pole",
        hovertemplate="<b>%{y}</b><br>Mediana grid: %{x}<br>%{text}<extra></extra>",
    ))
    fig6.update_layout(
        **PLOTLY_LAYOUT,
        title=titulo,
        xaxis_title="Posición de salida del ganador",
        yaxis_title="",
        height=420,
        legend=dict(orientation="h", y=1.05),
    )
    st.plotly_chart(fig6, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# VIZ 5 — EDAD DE GANADORES (Funciones de fecha + Window)
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    '<div class="section-title">05 · Edad — ¿La F1 premia a pilotos más jóvenes?</div>',
    unsafe_allow_html=True
)
st.caption(
    "SQL: DATE_PART(), AGE(), LAG() OVER, PERCENTILE_CONT() · "
    "Evolución de la edad promedio de los ganadores 1950–2024"
)

df_edad = load_edad_ganadores()
df_edad_f = df_edad[df_edad["era_f1"].isin(eras_sel)] if eras_sel else df_edad

fig7 = go.Figure()

# Banda de rango min-max por era
for era, grp in df_edad_f.groupby("era_f1"):
    color = ERA_COLORS.get(era, "#888")
    fig7.add_trace(go.Scatter(
        x=list(grp["temporada"]) + list(grp["temporada"])[::-1],
        y=list(grp["edad_max"]) + list(grp["edad_min"])[::-1],
        fill="toself",
        fillcolor=color.replace("#", "rgba(") + ",0.12)" if color.startswith("#")
            else color,
        line=dict(color="rgba(0,0,0,0)"),
        name=f"{era} (rango)",
        showlegend=False,
        hoverinfo="skip",
    ))

# Línea de edad promedio
for era, grp in df_edad_f.groupby("era_f1"):
    color = ERA_COLORS.get(era, "#888")
    fig7.add_trace(go.Scatter(
        x=grp["temporada"], y=grp["avg_edad"],
        mode="lines+markers",
        line=dict(color=color, width=2.5),
        marker=dict(size=5),
        name=era,
        hovertemplate="<b>%{x}</b><br>Edad promedio: %{y}<extra>" + era + "</extra>",
    ))

fig7.add_hline(
    y=df_edad_f["avg_edad"].mean(), line_dash="dot",
    line_color="#555", line_width=1,
    annotation_text=f"Media histórica: {df_edad_f['avg_edad'].mean():.1f} años",
    annotation_font_color="#888",
)
fig7.update_layout(
    **PLOTLY_LAYOUT,
    title="Edad promedio de los ganadores de carrera por temporada",
    xaxis_title="Temporada",
    yaxis_title="Edad (años)",
    height=380,
)
st.plotly_chart(fig7, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="f1-footer">
  F1 Analytics · Proyecto Final Módulo 4 BI y SQL Avanzado ·
  Dataset: Ergast F1 Database 1950–2024 · Aurora PostgreSQL
</div>
""", unsafe_allow_html=True)
