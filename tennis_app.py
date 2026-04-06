import streamlit as st
import requests
import pandas as pd
import plotly.express as px

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Pro Tennis Analytics", layout="wide")

# --- MOTOR DE SCRAPING ROBUSTO ---
@st.cache_data(ttl=3600)
def get_abstract_data(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # Intentar leer todas las tablas y buscar la que tenga datos de tenis
        tables = pd.read_html(response.text, flavor='lxml')
        
        # Seleccionamos la tabla que contiene la columna 'Player'
        df = None
        for t in tables:
            if 'Player' in t.columns or (isinstance(t.columns, pd.MultiIndex) and 'Player' in t.columns.get_level_values(-1)):
                df = t
                break
        
        if df is None: return pd.DataFrame()
        
        # Limpieza de MultiIndex
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(-1)
        
        # Limpieza de nombres de columnas y conversión numérica
        df.columns = [str(c).replace('\xa0', ' ').strip() for c in df.columns]
        
        for col in df.columns:
            if any(x in str(col) for x in ['%', 'Pt', 'Elo', 'Wnr', 'UFE', 'Ratio', 'Matches']):
                df[col] = pd.to_numeric(df[col].astype(str).str.replace('%', '').str.replace('+', ''), errors='coerce')
        
        return df
    except Exception as e:
        st.error(f"Error cargando datos de {url}: {e}")
        return pd.DataFrame()

# --- BARRA LATERAL ---
st.sidebar.header("Control Panel")
tour = st.sidebar.selectbox("Select Tour:", ["WTA", "ATP"])
min_matches = st.sidebar.slider("Min Matches:", 0, 100, 15)

# --- CARGA DE DATOS ---
with st.spinner('Analizando estadísticas de la gira...'):
    # Carga de Elo
    df_elo = get_abstract_data(f"https://tennisabstract.com/reports/{tour.lower()}_elo_ratings.html")
    
    # Carga de Ganadores/Errores (Basado en tu imagen)
    df_we = get_abstract_data(f"https://tennisabstract.com/reports/winners_errors_leaders_{'women' if tour == 'WTA' else 'men'}_last52.html")

# --- INTERFAZ PRINCIPAL ---
st.title(f"🎾 {tour} Intelligence Dashboard")

tab1, tab2, tab3 = st.tabs(["📊 Elo Ratings", "🔥 Winners & Errors", "🛡️ Return/Serve"])

with tab1:
    if not df_elo.empty:
        st.subheader("Top 15 Elo Leaders")
        df_plot = df_elo.sort_values('Elo', ascending=False).head(15)
        fig = px.bar(df_plot, x='Elo', y='Player', orientation='h', template="plotly_dark", color='Elo')
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(df_elo)

with tab2:
    if not df_we.empty:
        df_we = df_we[df_we['Matches'] >= min_matches]
        st.subheader("Análisis de Agresividad: Winners vs UFEs") #
        fig_we = px.scatter(
            df_we, x='Wnr/Pt', y='UFE/Pt', text='Player', size='Ratio',
            color='Ratio', template="plotly_dark", height=600
        )
        st.plotly_chart(fig_we, use_container_width=True)
        st.dataframe(df_we)

with tab3:
    st.info("Utiliza las pestañas superiores para profundizar en Rally Length y Return Stats.") #
