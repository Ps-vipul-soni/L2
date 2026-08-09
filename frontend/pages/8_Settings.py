import streamlit as st
import requests
import os

st.set_page_config(page_title="Settings", layout="wide")
st.title("Settings")

st.markdown("This page displays read-only system configuration and status.")

# 1. API URL
API_BASE = os.environ.get("API_URL", "http://127.0.0.1:8000")
st.subheader("System Configuration")
st.info(f"**Backend API URL:** `{API_BASE}`")

# 2. Application Version
st.info("**Application Version:** Not currently versioned")

# 3. Neo4j Status
st.subheader("Database Status")
with st.spinner("Checking Neo4j connection..."):
    try:
        res = requests.get(f"{API_BASE}/health/neo4j", timeout=5)
        if res.status_code == 200:
            status = res.json().get("status")
            if status == "connected":
                st.success("✅ **Neo4j Status:** Connected")
            else:
                detail = res.json().get("detail", "Unknown error")
                st.error(f"❌ **Neo4j Status:** Disconnected ({detail})")
        else:
            st.error(f"❌ **Neo4j Status:** Error {res.status_code}")
    except requests.exceptions.RequestException as e:
        st.error(f"❌ **Neo4j Status:** Connection Failed ({e})")

# 4. Supported Regulations
st.subheader("Supported Regulations")
with st.spinner("Loading regulations..."):
    try:
        res = requests.get(f"{API_BASE}/regulations")
        if res.status_code == 200:
            regs = res.json()
            if regs:
                for r in regs:
                    st.markdown(f"- **{r.get('code', 'N/A')}**: {r.get('name', 'N/A')}")
            else:
                st.warning("No regulations found in the database.")
        else:
            st.error(f"Failed to fetch regulations: {res.status_code}")
    except requests.exceptions.RequestException as e:
        st.error(f"Failed to connect to API to fetch regulations: {e}")
