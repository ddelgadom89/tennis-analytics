import streamlit as st
import requests
import pandas as pd
import plotly.express as px

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Pro Tennis Analytics", layout="wide")

# --- MOTOR DE SCRAPING UNIVERSAL ---
@st.cache_data(ttl=3600)
def get_abstract_data(url, table_id='reportable'):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        tables = pd.read_html(response.text, attrs={'id': table_id})
        if not tables: return pd.DataFrame()
        df = tables[0]
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(-1)
        
        # Limpieza profunda de cabeceras
        df.columns = [str(c).replace('\xa0', ' ').replace('\n', '').strip() for c in df.columns]
        
        keywords = ['%', 'Pt', 'Elo', 'Age', 'Rank', 'Wnr', 'UFE', 'Ace', 'DF', '1st', '2nd', 'Hold', 'Ret', 'Brk', 'Won', 'Length', 'Matches']
        for col in df.columns:
            if any(x in str(col) for x in keywords):
                df[col] = pd.to_numeric(df[col].astype(str).str.replace('%', ''), errors='coerce')
        return df
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return pd.DataFrame()

# --- BARRA LATERAL ---
st.sidebar.header("Control Panel")
selected_tours = st.sidebar.multiselect("Select Elo Tour:", ["ATP", "WTA"], default=["WTA"])
min_matches = st.sidebar.slider("Min Matches Played (Last 52W):", 0, 100, 15)

if st.sidebar.button('🔄 Refresh All Intelligence'):
    st.cache_data.clear()
    st.rerun()

def filter_by_matches(df, threshold):
    if 'Matches' in df.columns:
        return df[df['Matches'] >= threshold].copy()
    return df

# --- CARGA DE DATOS ELO ---
with st.spinner('Synchronizing Global Databases...'):
    elo_frames = []
    for t in selected_tours:
        tmp_df = get_abstract_data(f"http://tennisabstract.com/reports/{t.lower()}_elo_ratings.html")
        if not tmp_df.empty:
            tmp_df['Tour'] = t
            elo_frames.append(tmp_df)
    df_elo_raw = pd.concat(elo_frames, ignore_index=True) if elo_frames else pd.DataFrame()

if not df_elo_raw.empty:
    df_elo = df_elo_raw.dropna(axis=1, how='all').copy()
    all_cols = df_elo.columns.tolist()
    off_rank_col = next((c for c in all_cols if 'rank' in c.lower() and 'elo' not in c.lower()), None)
    elo_rank_col = next((c for c in all_cols if 'elo' in c.lower() and 'rank' in c.lower()), None)
    df_elo['Rank_Diff'] = df_elo[off_rank_col] - df_elo[elo_rank_col] if off_rank_col and elo_rank_col else 0

# --- FUNCIÓN PARA SCATTERS ---
def draw_smart_scatter(df, x, y, color_col, title):
    fig = px.scatter(
        df, x=x, y=y, text="Player", color=color_col,
        template="plotly_dark", height=800,
        title=title,
        color_continuous_scale="Viridis"
    )
    fig.update_traces(
        textposition='top center',
        marker=dict(size=12, line=dict(width=1, color='white')),
        hoverinfo='all'
    )
    return fig

# --- INTERFAZ PRINCIPAL ---
st.title("🎾 Pro Tennis Intelligence Dashboard")

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📊 Global Elo", "🔬 Discrepancy", "🔥 Winners/Errors", "⚡ Service", "🛡️ Return", "🏃 Rally Depth", "📖 Glossary"
])

with tab1:
    if not df_elo_raw.empty:
        surface_map = {"Overall": "Elo", "Hard": "hElo", "Clay": "cElo", "Grass": "gElo"}
        selected_surf = st.selectbox("Rank by Surface:", list(surface_map.keys()))
        target_col = surface_map[selected_surf]
        df_surf = df_elo.sort_values(target_col, ascending=False).dropna(subset=[target_col])
        st.plotly_chart(px.bar(df_surf.head(15), x=target_col, y="Player", orientation='h', template="plotly_dark"), use_container_width=True)
        st.dataframe(df_surf, hide_index=True, use_container_width=True)

with tab2:
    if not df_elo_raw.empty:
        df_plot = df_elo.head(40).copy().sort_values('Rank_Diff', ascending=True)
        df_plot['Status'] = df_plot['Rank_Diff'].apply(lambda x: 'Underestimated' if x > 0 else 'Overestimated' if x < 0 else 'Aligned')
        st.plotly_chart(px.bar(df_plot, x='Rank_Diff', y='Player', color='Status', orientation='h', height=800, template="plotly_dark"), use_container_width=True)

with tab3:
    st.subheader("Winners & Errors Analytics")
    we_tour = st.radio("Select Circuit:", ["WTA", "ATP"], horizontal=True, key="we_tour")
    df_we = get_abstract_data(f"https://tennisabstract.com/reports/winners_errors_leaders_{'women' if we_tour == 'WTA' else 'men'}_last52.html")
    df_we = filter_by_matches(df_we, min_matches)
    if not df_we.empty:
        cols = [c for c in df_we.columns if c != 'Player']
        c1, c2 = st.columns(2)
        with c1: x_ax = st.selectbox("X-Axis:", cols, index=min(4, len(cols)-1), key="we_x")
        with c2: y_ax = st.selectbox("Y-Axis:", cols, index=min(5, len(cols)-1), key="we_y")
        st.plotly_chart(draw_smart_scatter(df_we, x_ax, y_ax, "Ratio" if "Ratio" in df_we.columns else x_ax, "Precision vs Power"), use_container_width=True)
        st.dataframe(df_we, hide_index=True, use_container_width=True)

with tab4:
    st.subheader("Service Leaders Analysis")
    serve_tour = st.radio("Select Circuit:", ["WTA", "ATP"], horizontal=True, key="serve_tour")
    df_serve = get_abstract_data(f"https://tennisabstract.com/reports/mcp_leaders_serve_{'women' if serve_tour == 'WTA' else 'men'}_last52.html")
    df_serve = filter_by_matches(df_serve, min_matches)
    if not df_serve.empty:
        avail = [c for c in df_serve.columns if c != 'Player']
        c1, c2 = st.columns(2)
        idx_x = avail.index("Ace%") if "Ace%" in avail else 0
        idx_y = avail.index("Hold%") if "Hold%" in avail else min(1, len(avail)-1)
        with c1: sx = st.selectbox("X-Axis:", avail, index=idx_x, key="serve_x")
        with c2: sy = st.selectbox("Y-Axis:", avail, index=idx_y, key="serve_y")
        st.plotly_chart(draw_smart_scatter(df_serve, sx, sy, sy, "Service Dominance"), use_container_width=True)
        st.dataframe(df_serve, hide_index=True, use_container_width=True)

with tab5:
    st.subheader("Return Games Intelligence")
    ret_tour = st.radio("Select Circuit:", ["WTA", "ATP"], horizontal=True, key="ret_tour")
    df_ret = get_abstract_data(f"https://tennisabstract.com/reports/mcp_leaders_return_{'women' if ret_tour == 'WTA' else 'men'}_last52.html")
    df_ret = filter_by_matches(df_ret, min_matches)
    if not df_ret.empty:
        r_cols = [c for c in df_ret.columns if c != 'Player']
        c1, c2 = st.columns(2)
        with c1: rx = st.selectbox("X-Axis:", r_cols, index=0, key="ret_x")
        with c2: ry = st.selectbox("Y-Axis:", r_cols, index=min(1, len(r_cols)-1), key="ret_y")
        st.plotly_chart(draw_smart_scatter(df_ret, rx, ry, ry, "Return Effectiveness"), use_container_width=True)
        st.dataframe(df_ret, hide_index=True, use_container_width=True)

with tab6:
    st.subheader("Rally Length & Performance")
    ral_tour = st.radio("Select Circuit:", ["WTA", "ATP"], horizontal=True, key="ral_tour")
    df_ral = get_abstract_data(f"https://tennisabstract.com/reports/mcp_leaders_rally_{'women' if ral_tour == 'WTA' else 'men'}_last52.html")
    df_ral = filter_by_matches(df_ral, min_matches)
    if not df_ral.empty:
        ral_cols = [c for c in df_ral.columns if c != 'Player']
        c1, c2 = st.columns(2)
        with c1: rax = st.selectbox("X-Axis:", ral_cols, index=0, key="ral_x")
        with c2: ray = st.selectbox("Y-Axis:", ral_cols, index=min(1, len(ral_cols)-1), key="ral_y")
        st.plotly_chart(draw_smart_scatter(df_ral, rax, ray, ray, "Rally Depth Analysis"), use_container_width=True)
        st.dataframe(df_ral, hide_index=True, use_container_width=True)

with tab7:
    st.header("📖 Intelligence Glossary")
    st.markdown("""
    ### 📊 Ranking & Elo Metrics
    * **Elo Rating:** A skill measurement where defeating a strong opponent grants more points than defeating a weak one.
    * **hElo / cElo / gElo:** Elo ratings specifically for Hard, Clay, and Grass courts.
    * **Rank_Diff:** The difference between official ATP/WTA ranking and Elo ranking. 
        * *Positive:* Player is playing better than their official rank suggests (Underestimated).
        * *Negative:* Official rank is higher than their current performance (Overestimated).

    ### 🔥 Aggression Metrics
    * **Wnr/Pt:** Winners hit per point played. High values indicate an aggressive style.
    * **UFE/Pt:** Unforced Errors per point played. High values indicate high-risk play or lack of consistency.
    * **Ratio:** Winners divided by Unforced Errors. A value > 1.0 means the player hits more winners than mistakes.

    ### ⚡ Service & Return Metrics
    * **Ace%:** Percentage of service points that are aces.
    * **Hold%:** Percentage of service games won.
    * **Break%:** Percentage of return games where the player breaks the opponent's serve.
    * **RiP% (Return in Play):** Percentage of returns successfully put into play.

    ### 🏃 Rally Metrics
    * **RallyLen:** Average number of shots per rally.
    * **1-3 W%:** Win percentage in short rallies (under 4 shots).
    * **4-6 W% / 7-9 W%:** Win percentage in medium-length rallies.
    * **10+ W%:** Win percentage in long, endurance rallies.
    """)