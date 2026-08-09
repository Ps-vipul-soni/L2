import requests
import pandas as pd
import streamlit as st

API_BASE = "http://127.0.0.1:8000"

st.set_page_config(page_title="Supplier Risk Analytics", layout="wide")
st.title("Supplier Risk Analytics")

st.markdown("""
This analytics page identifies which suppliers are exposing the supply chain to restricted chemicals.
It is powered by combining Neo4j graph topology (Supplier ➔ Component ➔ Ingredient) with PostgreSQL screening results.
""")

@st.cache_data(ttl=60)
def fetch_ranked_suppliers():
    try:
        res = requests.get(f"{API_BASE}/suppliers/risk")
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        st.error(f"Failed to fetch supplier risk data: {e}")
    return []

def fetch_supplier_graph(supplier_id):
    try:
        res = requests.get(f"{API_BASE}/suppliers/{supplier_id}/graph")
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        st.error(f"Failed to fetch supplier graph: {e}")
    return None

suppliers = fetch_ranked_suppliers()

if not suppliers:
    st.info("No supplier data available.")
    st.stop()

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("High Risk Suppliers")
    
    # Format for chart
    df = pd.DataFrame(suppliers)
    if not df.empty:
        df_chart = df[["supplier_name", "flagged_ingredient_count"]].set_index("supplier_name")
        st.bar_chart(df_chart, color="#ff4b4b")
        
        st.dataframe(
            df[["supplier_name", "flagged_ingredient_count"]], 
            use_container_width=True,
            column_config={
                "supplier_name": "Supplier Name",
                "flagged_ingredient_count": "Flagged Ingredients (Distinct)"
            },
            hide_index=True
        )

with col2:
    st.subheader("Supplier Drill-Down")
    
    supplier_options = {s["supplier_id"]: f"{s['supplier_name']} ({s['flagged_ingredient_count']} flagged)" for s in suppliers}
    selected_id = st.selectbox(
        "Select a supplier to trace their components:",
        options=list(supplier_options.keys()),
        format_func=lambda x: supplier_options[x]
    )
    
    if selected_id:
        graph_data = fetch_supplier_graph(selected_id)
        if graph_data:
            st.markdown(f"### Topology: {supplier_options[selected_id].split(' (')[0]}")
            
            components = graph_data.get("components", [])
            if not components:
                st.info("No components linked to this supplier in the graph.")
            
            for comp in components:
                with st.expander(f"📦 Component: {comp['component_name']}", expanded=False):
                    ingredients = comp.get("ingredients", [])
                    if not ingredients:
                        st.caption("No ingredients found for this component.")
                    
                    for ing in ingredients:
                        status = ing["overall_status"]
                        name = ing.get("name", "Unknown")
                        cas = ing.get("cas_number", "No CAS")
                        
                        if status == "FLAGGED":
                            icon = "🔴"
                            color = "red"
                        elif status == "ALLOWED":
                            icon = "🟢"
                            color = "green"
                        else:
                            icon = "⚪"
                            color = "gray"
                            
                        st.markdown(f"**{icon} {name}** (CAS: {cas}) - <span style='color:{color}'>{status}</span>", unsafe_allow_html=True)
                        
                        # Show details if flagged
                        if status == "FLAGGED":
                            for det in ing.get("details", []):
                                if det["status"] in ("RESTRICTED", "THRESHOLD_EXCEEDED"):
                                    st.caption(f"↳ {det['regulation_code']}: {det['status']}")
