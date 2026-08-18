import streamlit as st
import requests
import pandas as pd

API_BASE = "http://127.0.0.1:8000"

st.set_page_config(page_title="Dashboard", layout="wide")
st.title("Compliance Dashboard")

def fetch_summary():
    try:
        res = requests.get(f"{API_BASE}/dashboard/summary")
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        st.error(f"Failed to connect to backend: {e}")
    return None

data = fetch_summary()

if not data:
    st.warning("No data available from the backend or API is down.")
    st.stop()

st.header("Portfolio Overview")
col1, col2, col3 = st.columns(3)
col4, col5 = st.columns([1, 1])

with col1:
    st.metric("Products Screened", data.get("products_screened_count", 0))

with col2:
    st.metric("Ingredients Identified", data.get("ingredients_identified_count", 0))

with col3:
    st.metric("Regulations Evaluated", data.get("regulations_evaluated_count", 0))

with col4:
    comp_rate = data.get("compliance_rate")
    if comp_rate is None:
        st.metric("Compliance Rate", "No data yet")
    else:
        st.metric("Compliance Rate", f"{comp_rate:.1f}%")

with col5:
    st.metric("Open Manual Reviews", data.get("open_manual_reviews_count", 0))

st.markdown("---")
st.header("Compliance Status")

st.subheader("PASS/FAIL Distribution")
dist = data.get("pass_fail_distribution", {})
if not dist:
    st.info("No completed screening runs yet")
else:
    # Streamlit bar_chart expects a dataframe where index is category and column is value
    df_dist = pd.DataFrame(list(dist.items()), columns=["Status", "Count"])
    df_dist.set_index("Status", inplace=True)
    st.bar_chart(df_dist)

st.markdown("---")
st.header("Regulatory Violations & Restricted Substances")

colC, colD = st.columns(2)

with colC:
    st.subheader("Top 5 Violated Regulations")
    top_regs = data.get("top_violated_regulations", [])
    if not top_regs:
        st.info("No regulatory violations recorded yet")
    else:
        df_regs = pd.DataFrame(top_regs)
        df_regs.set_index("regulation_code", inplace=True)
        st.bar_chart(df_regs)

with colD:
    st.subheader("Top 5 Most Common Restricted Substances")
    top_subs = data.get("most_common_restricted_substances", [])
    if not top_subs:
        st.info("No restricted substances identified yet")
    else:
        df_subs = pd.DataFrame(top_subs)
        df_subs.set_index("canonical_name", inplace=True)
        st.bar_chart(df_subs)
