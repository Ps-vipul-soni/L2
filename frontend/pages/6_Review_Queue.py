import time
import requests
import streamlit as st
from datetime import datetime

API_BASE = "http://127.0.0.1:8000"

st.set_page_config(page_title="Review Queue", layout="wide")
st.title("Review Queue")

st.markdown("""
    **Note on Timestamps**: The `Created` tracking was added in Review Queue V2. 
    Items generated before this update will display the time the migration was applied, rather than their true historical creation time.
""")

# --- State Management ---
if "rq_filters" not in st.session_state:
    st.session_state.rq_filters = {
        "status": "OPEN",
        "review_type": "ALL"
    }

# --- Filters ---
with st.expander("Filter Queue", expanded=True):
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        status_filter = st.selectbox(
            "Status", 
            ["OPEN", "RESOLVED", "ALL"],
            index=["OPEN", "RESOLVED", "ALL"].index(st.session_state.rq_filters["status"])
        )
    with col2:
        type_filter = st.selectbox(
            "Review Type", 
            ["ALL", "EXTRACTION", "SCREENING"],
            index=["ALL", "EXTRACTION", "SCREENING"].index(st.session_state.rq_filters["review_type"])
        )
    with col3:
        st.write("") # spacing
        st.write("") # spacing
        if st.button("Apply Filters", type="primary"):
            st.session_state.rq_filters["status"] = status_filter
            st.session_state.rq_filters["review_type"] = type_filter
            st.rerun()

# --- Data Fetching ---
def fetch_queue():
    try:
        params = {
            "status": st.session_state.rq_filters["status"],
            "review_type": st.session_state.rq_filters["review_type"]
        }
        res = requests.get(f"{API_BASE}/pipeline/review-queue", params=params)
        if res.status_code == 200:
            return res.json()
        else:
            st.error(f"Failed to fetch queue: {res.text}")
    except Exception as e:
        st.error(f"Connection error: {e}")
    return []

queue_items = fetch_queue()

# --- Rendering ---
if queue_items:
    for item in queue_items:
        with st.container(border=True):
            # 1. Created At
            created_str = item.get("created_at")
            if created_str:
                dt = datetime.fromisoformat(created_str)
                st.caption(f"**Created:** {dt.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                st.caption("**Created:** Unknown")

            # 2. Reference Header
            if item.get("product_name") and item.get("ingredient_name"):
                display_name = f"Product: {item['product_name']} | Ingredient: {item['ingredient_name']}"
            elif item.get("filename"):
                display_name = item.get("filename")
            else:
                display_name = f"Screening Result Reference: {item.get('screening_result_id')}"
                
            st.subheader(display_name)
            
            # 3. Category label using substring/keyword matching
            reason_raw = item.get("reason", "")
            reason_lower = reason_raw.lower()
            
            if "extraction" in reason_lower:
                label = "⚠️ Low Confidence Extraction"
                st.error(label)
            elif "screening" in reason_lower:
                label = "⚠️ Screening Judgment Needs Review"
                st.warning(label)
            else:
                label = "⚠️ Manual Review Required"
                st.info(label)
                
            # 4. FULL raw reason text
            st.markdown(f"**Details:** {reason_raw}")
            
            # 5. Status
            st.caption(f"Status: {item.get('status', 'OPEN')}")
            
            # 6. UUIDs in a collapsible Developer Details expander
            with st.expander("Developer Details"):
                dev_details = {
                    "review_id": item.get("id"),
                    "document_id": item.get("document_id"),
                    "screening_result_id": item.get("screening_result_id")
                }
                # ONLY show workflow_run_id if genuinely returned
                if item.get("workflow_run_id"):
                    dev_details["workflow_run_id"] = item["workflow_run_id"]
                    
                st.json(dev_details)
            
            # 7. Action Button
            if item.get("status") == "OPEN":
                if st.button("Mark as Manually Reviewed", key=f"btn_{item['id']}", help="This records that you've handled this review manually. It does not generate a compliance report or complete the workflow."):
                    try:
                        res = requests.post(f"{API_BASE}/pipeline/review-queue/{item['id']}/resolve")
                        if res.status_code == 200:
                            st.toast("Item resolved successfully.")
                            time.sleep(0.5)
                            st.rerun()
                        elif res.status_code == 409:
                            st.error("This item has already been resolved or modified by another user.")
                        else:
                            st.error(f"Failed to resolve: {res.status_code}")
                    except Exception as e:
                        st.error(f"Connection error: {e}")
else:
    st.info("✅ No review items match the selected filters.")
