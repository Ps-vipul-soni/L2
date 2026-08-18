import streamlit as st
import requests
import pandas as pd

API_BASE = "http://127.0.0.1:8000"

st.set_page_config(page_title="Screening Results", layout="wide")
st.title("Screening Results")
st.markdown("Browse screening results across all products and workflow runs.")

# --- Data Fetching ---
@st.cache_data(ttl=60)
def get_products():
    try:
        res = requests.get(f"{API_BASE}/products")
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return []

@st.cache_data(ttl=60)
def get_regulations():
    try:
        res = requests.get(f"{API_BASE}/regulations")
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return []

def fetch_screening_results(params):
    try:
        res = requests.get(f"{API_BASE}/screening-results", params=params)
        if res.status_code == 200:
            return res.json()
        else:
            st.error(f"Failed to fetch results: {res.text}")
    except Exception as e:
        st.error(f"Connection error: {e}")
    return {"results": [], "truncated": False}

products = get_products()
product_options = {"All": None}
for p in products:
    product_options[p["name"]] = p["id"]

regulations = get_regulations()
reg_options = {"All": None}
for r in regulations:
    reg_options[r["code"]] = r["code"]

STATUS_OPTIONS = {
    "All": None,
    "RESTRICTED": "RESTRICTED",
    "ALLOWED": "ALLOWED",
    "THRESHOLD_EXCEEDED": "THRESHOLD_EXCEEDED",
    "EXEMPTION_AVAILABLE": "EXEMPTION_AVAILABLE",
    "NEEDS_REVIEW": "NEEDS_REVIEW"
}

# --- State Management ---
if "filters" not in st.session_state:
    st.session_state.filters = {
        "product_id": None,
        "regulation_code": None,
        "status": None,
        "ingredient": ""
    }
    
if "trigger_search" not in st.session_state:
    st.session_state.trigger_search = True

def clear_filters():
    st.session_state.filters = {
        "product_id": None,
        "regulation_code": None,
        "status": None,
        "ingredient": ""
    }
    st.session_state.trigger_search = True

# --- UI Filters ---
with st.expander("Filter Results", expanded=True):
    with st.form("filter_form"):
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            sel_prod = st.selectbox(
                "Product", 
                options=list(product_options.keys()),
                index=list(product_options.values()).index(st.session_state.filters["product_id"]) if st.session_state.filters["product_id"] in product_options.values() else 0
            )
            
        with col2:
            sel_reg = st.selectbox(
                "Regulation", 
                options=list(reg_options.keys()),
                index=list(reg_options.values()).index(st.session_state.filters["regulation_code"]) if st.session_state.filters["regulation_code"] in reg_options.values() else 0
            )
            
        with col3:
            sel_stat = st.selectbox(
                "Status", 
                options=list(STATUS_OPTIONS.keys()),
                index=list(STATUS_OPTIONS.values()).index(st.session_state.filters["status"]) if st.session_state.filters["status"] in STATUS_OPTIONS.values() else 0
            )
            
        with col4:
            sel_ing = st.text_input("Ingredient (CAS or Name)", value=st.session_state.filters["ingredient"])
            
        colA, colB = st.columns([1, 10])
        with colA:
            submitted = st.form_submit_button("Apply Filters", type="primary")
        with colB:
            st.form_submit_button("Clear Filters", on_click=clear_filters)
            
        if submitted:
            st.session_state.filters["product_id"] = product_options[sel_prod]
            st.session_state.filters["regulation_code"] = reg_options[sel_reg]
            st.session_state.filters["status"] = STATUS_OPTIONS[sel_stat]
            st.session_state.filters["ingredient"] = sel_ing
            st.session_state.trigger_search = True

# --- Fetch Data ---
if st.session_state.trigger_search:
    params = {}
    if st.session_state.filters["product_id"]: params["product_id"] = st.session_state.filters["product_id"]
    if st.session_state.filters["regulation_code"]: params["regulation_code"] = st.session_state.filters["regulation_code"]
    if st.session_state.filters["status"]: params["status"] = st.session_state.filters["status"]
    if st.session_state.filters["ingredient"].strip(): params["ingredient"] = st.session_state.filters["ingredient"].strip()
    
    data = fetch_screening_results(params)
    st.session_state.cached_results = data
    st.session_state.trigger_search = False

# --- Render Results ---
data = st.session_state.get("cached_results", {"results": [], "truncated": False})
results = data["results"]

if data["truncated"]:
    st.warning("⚠️ The result set exceeded 500 rows. Only the first 500 are shown. Please narrow your filters to see specific records.")

if not results:
    # Determine if the database is truly empty or just the query yielded zero matches
    if not any(st.session_state.filters.values()):
        st.info("No screening results are available yet.")
    else:
        st.info("No screening results match the selected filters.")
else:
    df = pd.DataFrame(results)
    
    # Map emojis for status
    status_map = {
        "RESTRICTED": "🔴 RESTRICTED",
        "THRESHOLD_EXCEEDED": "🔴 THRESHOLD_EXCEEDED",
        "ALLOWED": "🟢 ALLOWED",
        "EXEMPTION_AVAILABLE": "🟢 EXEMPTION_AVAILABLE",
        "NEEDS_REVIEW": "🟡 NEEDS_REVIEW"
    }
    df["status"] = df["status"].apply(lambda x: status_map.get(x, x))
    
    # Reorder and rename columns
    display_df = df[[
        "product_name", "component_name", "canonical_name", "cas_number", 
        "regulation_code", "measured_value", "threshold_value", 
        "status", "confidence", "created_at", "workflow_run_id"
    ]].copy()
    
    display_df.rename(columns={
        "product_name": "Product",
        "component_name": "Component",
        "canonical_name": "Ingredient",
        "cas_number": "CAS",
        "regulation_code": "Regulation",
        "measured_value": "Measured Value",
        "threshold_value": "Allowed Limit",
        "status": "Status",
        "confidence": "Confidence",
        "created_at": "Created At"
    }, inplace=True)
    
    # Configure the link column for "workflow_run_id"
    display_df["workflow_run_id"] = display_df["workflow_run_id"].apply(lambda x: f"/Compliance_Reports?workflow_run_id={x}")
    
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "workflow_run_id": st.column_config.LinkColumn(
                "Action",
                display_text="View Report",
                help="Click to open the full Compliance Report for this run"
            )
        }
    )
