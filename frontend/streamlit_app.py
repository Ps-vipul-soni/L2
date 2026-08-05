import os
import time
import requests
import streamlit as st

API_BASE = "http://127.0.0.1:8000"

st.set_page_config(page_title="Compliance Screening", layout="wide")
st.title("Compliance Screening Pipeline")

# Initialize session state for document
if "document_id" not in st.session_state:
    st.session_state.document_id = None
if "workflow_run_id" not in st.session_state:
    st.session_state.workflow_run_id = None

# --- Fetch Products ---
@st.cache_data(ttl=60)
def get_products():
    try:
        res = requests.get(f"{API_BASE}/products")
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        st.error(f"Failed to connect to API: {e}")
    return []

products = get_products()
if not products:
    st.warning("No products found or API is down. Please ensure the backend is running.")
    st.stop()

product_options = {p["name"]: p["id"] for p in products}

# --- SECTION 1: Upload ---
st.header("1. Upload Document")
selected_product_name = st.selectbox("Select Product", options=list(product_options.keys()))
uploaded_file = st.file_uploader("Upload SDS, BOM, or FMD", type=["pdf", "csv", "xls", "xlsx", "xml"])

if st.button("Upload"):
    if not uploaded_file:
        st.error("Please select a file first.")
    else:
        with st.spinner("Uploading..."):
            try:
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                data = {"product_id": product_options[selected_product_name]}
                res = requests.post(f"{API_BASE}/documents/upload", files=files, data=data)
                
                if res.status_code == 200:
                    st.session_state.document_id = res.json()["document_id"]
                    st.success(f"Uploaded successfully! Document ID: {st.session_state.document_id}")
                else:
                    st.error(f"Upload failed: {res.json().get('detail', res.text)}")
            except Exception as e:
                st.error(f"Connection error: {e}")

# --- SECTION 2: Pipeline Trigger ---
st.header("2. Run Pipeline")
if st.session_state.document_id:
    st.info(f"Ready to run pipeline for Document ID: {st.session_state.document_id}")
    
    if st.button("Trigger Pipeline"):
        st.session_state.workflow_run_id = None
        
        with st.spinner("Starting pipeline... this may take a moment."):
            try:
                res = requests.post(
                    f"{API_BASE}/pipeline/trigger", 
                    json={"document_id": st.session_state.document_id}
                )
                if res.status_code == 200:
                    st.session_state.workflow_run_id = res.json()["workflow_run_id"]
                    st.success(f"Pipeline started! Run ID: {st.session_state.workflow_run_id}")
                else:
                    st.error(f"Trigger failed: {res.json().get('detail', res.text)}")
            except Exception as e:
                st.error(f"Connection error: {e}")
                
        # Polling if started successfully
        if st.session_state.workflow_run_id:
            status_container = st.empty()
            
            # Polling loop (max 5 minutes = 300 seconds)
            max_retries = 150
            interval = 2
            
            for i in range(max_retries):
                try:
                    status_res = requests.get(f"{API_BASE}/pipeline/status/{st.session_state.workflow_run_id}")
                    if status_res.status_code == 200:
                        data = status_res.json()
                        status = data["status"]
                        
                        if status == "COMPLETED":
                            status_container.success("Pipeline Completed!")
                            st.subheader("Executive Report")
                            st.markdown(data.get("report", "No report content found."))
                            break
                        elif status == "PARTIAL":
                            status_container.warning("Pipeline routed to human review due to low confidence.")
                            break
                        elif status == "FAILED":
                            status_container.error("Pipeline failed!")
                            break
                        else:
                            status_container.info(f"Pipeline is {status}... (Polling {i+1}/{max_retries})")
                except Exception as e:
                    status_container.error(f"Polling error: {e}")
                    break
                    
                time.sleep(interval)
            else:
                status_container.error("Polling timeout reached (5 minutes). The workflow is taking longer than expected.")

else:
    st.write("Please upload a document first.")

# --- SECTION 3: Review Queue ---
st.header("3. Review Queue")
if st.button("Refresh Queue"):
    try:
        res = requests.get(f"{API_BASE}/pipeline/review-queue")
        if res.status_code == 200:
            queue_items = res.json()
            if queue_items:
                st.dataframe(queue_items, use_container_width=True)
            else:
                st.info("No open review items.")
        else:
            st.error(f"Failed to fetch queue: {res.status_code}")
    except Exception as e:
        st.error(f"Connection error: {e}")

