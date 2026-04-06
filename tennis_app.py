import streamlit as st
import requests
import pandas as pd
import plotly.express as px

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Pro Tennis Analytics", layout="wide")

# --- MOTOR DE SCRAPING ROBUSTO ---
@st.cache_data(ttl=3600)
def get_abstract_data(url, table_id='reportable'):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # Se intenta leer con lxml
        tables = pd.read_html(response.text, attrs={'id': table_id}, flavor='lxml')
        if not tables: 
            return pd.DataFrame()
            
        df = tables[0]
        
        # Colapsar MultiIndex si existe
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(-1)
        
        # LIMPIEZA CRÍTICA: Elimina caracteres invisibles y normaliza nombres
        df.columns = [
            str(c).replace('\xa0', ' ')
            .replace('\n', '')
            .strip() 
            for c in df.columns
        ]
        
        # Eliminar columnas duplicadas o vacías (común en este sitio)
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
        
        # Conversión numérica masiva
        keywords = ['%', 'Pt', 'Elo', 'Age', 'Rank', 'Wnr', 'UFE', 'Ace', 'DF', '1st', '2nd', 'Hold', 'Ret', 'Brk', 'Won', 'Length', 'Matches', 'W%', 'W/L', 'Ratio']
        for col in df.columns:
            if any(x in str(col) for x in keywords):
                # Limpieza de símbolos antes de convertir
                df[col] = (df[col].astype(str)
                           .str.replace('%', '')
                           .str.replace('+', '')
                           .str.replace('$', '')
                           .replace('nan', None))
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
        return df
    except Exception as e:
        st.error(f"Error en enlace {url}: {e}")
        return pd.DataFrame()

# --- BARRA LATERAL ---
st.sidebar.header("Control Panel")
selected_tours = st.sidebar.multiselect("Select Elo Tour:", ["ATP", "WTA"], default=["WTA"])
min_matches = st.sidebar.slider("Min Matches Played (Last 52W):", 0, 100, 15)

if st.sidebar.button('🔄 Refresh All Intelligence'):
    st.cache_data.clear()
    st.rerun()

def filter_by_matches(df, threshold):
    match_col = next((c for c in df.columns if 'Matches' in c), None)
    if match_col:
        return df[df[match_col] >= threshold].copy()
    return df

# --- CARGA DE DATOS ELO ---
with st.spinner('Synchronizing Global Databases...'):
    elo_frames = []
    for t in selected_tours:
        # Forzar HTTPS
        url_elo = f"https://tennisabstract.com/reports/{t.lower()}_elo_ratings.html"
        tmp_df = get_abstract_data(url_elo)
        if not tmp_df.empty:
            tmp_df['Tour'] = t
            elo_frames.append(tmp_df)
    
    if elo_frames:
        df_elo = pd.concat(elo_frames, ignore_index=True)
        # Cálculo de discrepancia
        all_cols = df_elo.columns.tolist()
        off_rank = next((c for c in all_cols if 'Rank' in c and 'Elo' not in c), None)
        elo_rank = next((c for c in all_cols if 'Elo' in c and 'Rank' in c), None)
        if off_rank and elo_rank:
            df_elo['Rank_Diff'] = df_elo[off_rank] - df_elo[elo_rank]
    else:
        df_elo = pd.DataFrame()

# --- FUNCION PARA GRAFICOS ---
def draw_smart_scatter(df, x, y, color_col, title):
    fig = px.scatter(
        df, x=x, y=y, text="Player", color=color_col,
        template="plotly_dark", height=700, title=title,
        color_continuous_scale="Viridis"
    )
    fig.update_traces(textposition='top center', marker=dict(size=10, line=dict(width=1, color='white')))
    return fig

# --- INTERFAZ ---
st.title("🎾 Pro Tennis Intelligence Dashboard")

if df_elo.empty:
    st.warning("No se pudieron cargar los datos. Verifica la conexión con Tennis Abstract.")
else:
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Global Elo", "🔬 Discrepancy", "🔥 Winners/Errors", "⚡ Service", "🛡️ Return", "🏃 Rally Depth"
    ])

    with tab1:
        surface_map = {"Overall": "Elo", "Hard": "hElo", "Clay": "cElo", "Grass": "gElo"}
        selected_surf = st.selectbox("Rank by Surface:", list(surface_map.keys()))
        target_col = surface_map[selected_surf]
        if target_col in df_elo.columns:
            df_surf = df_elo.sort_values(target_col, ascending=False).dropna(subset=[target_col])
            st.plotly_chart(px.bar(df_surf.head(15), x=target_col, y="Player", orientation='h', template="plotly_dark"), use_container_width=True)
            st.dataframe(df_surf, hide_index=True, use_container_width=True)

    with tab2:
        if 'Rank_Diff' in df_elo.columns:
            df_plot = df_elo.head(40).copy().sort_values('Rank_Diff', ascending=True)
            df_plot['Status'] = df_plot['Rank_Diff'].apply(lambda x: 'Underestimated' if x > 0 else 'Overestimated' if x < 0 else 'Aligned')
            st.plotly_chart(px.bar(df_plot, x='Rank_Diff', y='Player', color='Status', orientation='h', height=800, template="plotly_dark"), use_container_width=True)

    with tab3:
        we_tour = st.radio("Select Circuit:", ["WTA", "ATP"], horizontal=True, key="we_t")
        df_we = get_abstract_data(f"https://tennisabstract.com/reports/winners_errors_leaders_{'women' if we_tour == 'WTA' else 'men'}_last52.html")
        df_we = filter_by_matches(df_we, min_matches)
        if not df_we.empty:
            cols = [c for c in df_we.columns if c != 'Player']
            c1, c2 = st.columns(2)
            with c1: x_ax = st.selectbox("X-Axis:", cols, index=min(4, len(cols)-1), key="we_x")
            with c2: y_ax = st.selectbox("Y-Axis:", cols, index=min(5, len(cols)-1), key="we_y")
            st.plotly_chart(draw_smart_scatter(df_we, x_ax, y_ax, x_ax, "Precision vs Power"), use_container_width=True)
            st.dataframe(df_we, hide_index=True, use_container_width=True)

    with tab4:
        serve_tour = st.radio("Select Circuit:", ["WTA", "ATP"], horizontal=True, key="ser_t")
        df_serve = get_abstract_data(f"https://tennisabstract.com/reports/mcp_leaders_serve_{'women' if serve_tour == 'WTA' else 'men'}_last52.html")
        df_serve = filter_by_matches(df_serve, min_matches)
        if not df_serve.empty:
            avail = [c for c in df_serve.columns if c != 'Player']
            sx = st.selectbox("X-Axis:", avail, index=0, key="sx")
            sy = st.selectbox("Y-Axis:", avail, index=min(1, len(avail)-1), key="sy")
            st.plotly_chart(draw_smart_scatter(df_serve, sx, sy, sy, "Service Dominance"), use_container_width=True)

    with tab5:
        ret_tour = st.radio("Select Circuit:", ["WTA", "ATP"], horizontal=True, key="ret_t")
        df_ret = get_abstract_data(f"https://tennisabstract.com/reports/mcp_leaders_return_{'women' if ret_tour == 'WTA' else 'men'}_last52.html")
        df_ret = filter_by_matches(df_ret, min_matches)
        if not df_ret.empty:
            r_cols = [c for c in df_ret.columns if c != 'Player']
            rx = st.selectbox("X-Axis:", r_cols, key="rx")
            ry = st.selectbox("Y-Axis:", r_cols, index=min(1, len(r_cols)-1), key="ry")
            st.plotly_chart(draw_smart_scatter(df_ret, rx, ry, ry, "Return Effectiveness"), use_container_width=True)

    with tab6:
        ral_tour = st.radio("Select Circuit:", ["WTA", "ATP"], horizontal=True, key="ral_t")
        df_ral = get_abstract_data(f"https://tennisabstract.com/reports/mcp_leaders_rally_{'women' if ral_tour == 'WTA' else 'men'}_last52.html")
        df_ral = filter_by_matches(df_ral, min_matches)
        if not df_ral.empty:
            ral_cols = [c for c in df_ral.columns if c != 'Player']
            rax = st.selectbox("X-Axis:", ral_cols, key="rax")
            ray = st.selectbox("Y-Axis:", ral_cols, index=min(1, len(ral_cols)-1), key="ray")
            st.plotly_chart(draw_smart_scatter(df_ral, rax, ray, ray, "Rally Performance"), use_container_width=True)
 
