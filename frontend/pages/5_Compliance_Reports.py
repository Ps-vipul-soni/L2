import streamlit as st
import requests
import json
import pandas as pd

API_BASE = "http://127.0.0.1:8000"

st.set_page_config(page_title="Compliance Reports", layout="wide")
st.title("Compliance Reports")
st.markdown("View detailed compliance reports and screening results for completed product evaluations.")

# --- 1. Cascading UX for Loading Report ---
@st.cache_data(ttl=30)
def get_recent_reports():
    try:
        res = requests.get(f"{API_BASE}/reports/recent")
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return []

recent_runs = get_recent_reports()
recent_options = {f"{r['product_name']} ({r['completed_at'][:10]}) - {r['id']}": r["id"] for r in recent_runs}

selected_run_id = None

with st.container(border=True):
    st.subheader("Load Report")
    
    # Priority 1: query parameters or session_state (arriving from Product Screening or Screening Results)
    default_id = st.query_params.get("workflow_run_id", st.session_state.get("workflow_run_id", ""))
    
    col1, col2 = st.columns(2)
    with col1:
        # Priority 2: Dropdown of recents
        dropdown_selection = st.selectbox(
            "Recent Completed Runs", 
            options=[""] + list(recent_options.keys()), 
            index=0
        )
    with col2:
        # Priority 3: Manual entry (pre-filled with session state if available)
        manual_id = st.text_input("Or enter Workflow Run ID directly:", value=default_id)
        
    # We auto-trigger loading if a query param is explicitly passed.
    has_query_param = "workflow_run_id" in st.query_params
    
    if st.button("Load Report", type="primary") or has_query_param:
        if manual_id:
            selected_run_id = manual_id
        elif dropdown_selection:
            selected_run_id = recent_options[dropdown_selection]
        else:
            if not has_query_param:
                st.warning("Please select or enter a Workflow Run ID.")
            
# --- 2. Fetch and Render Report ---
if selected_run_id:
    st.divider()
    
    with st.spinner("Loading report data..."):
        try:
            # Fetch JSON report
            json_res = requests.get(f"{API_BASE}/reports/{selected_run_id}/export?format=json")
            
            if json_res.status_code == 200:
                report_data = json_res.json()
                
                # We also want to prepare the CSV payload for the download button
                csv_res = requests.get(f"{API_BASE}/reports/{selected_run_id}/export?format=csv")
                csv_payload = csv_res.text if csv_res.status_code == 200 else ""
                
                workflow = report_data.get("workflow_run", {})
                decision = report_data.get("compliance_decision", {})
                report_sections = report_data.get("report", {})
                screening_results = report_data.get("screening_results", [])
                
                # --- Top Metrics & Exports ---
                head_col1, head_col2, head_col3 = st.columns([1, 1, 2])
                with head_col1:
                    overall_status = decision.get("overall_status", "UNKNOWN") if decision else "UNKNOWN"
                    if overall_status == "PASS":
                        st.success(f"**Overall Status:** 🟢 {overall_status}")
                    elif overall_status == "WARNING":
                        st.warning(f"**Overall Status:** 🟡 {overall_status}")
                    else:
                        st.error(f"**Overall Status:** 🔴 {overall_status}")
                        
                with head_col2:
                    risk_score = decision.get("risk_score", "N/A") if decision else "N/A"
                    st.metric("Risk Score", risk_score)
                    
                with head_col3:
                    st.markdown("<div style='text-align: right;'>", unsafe_allow_html=True)
                    dl_col1, dl_col2 = st.columns(2)
                    with dl_col1:
                        st.download_button(
                            label="📥 Download JSON",
                            data=json.dumps(report_data, indent=2),
                            file_name=f"compliance_report_{selected_run_id}.json",
                            mime="application/json"
                        )
                    with dl_col2:
                        st.download_button(
                            label="📥 Download CSV",
                            data=csv_payload,
                            file_name=f"screening_results_{selected_run_id}.csv",
                            mime="text/csv",
                            disabled=not csv_payload
                        )
                    st.markdown("</div>", unsafe_allow_html=True)
                
                st.write(f"**Run ID:** `{selected_run_id}` | **Completed:** {workflow.get('completed_at', 'N/A')}")
                
                # --- Report Body (Expanders) ---
                st.subheader("Report Summary")
                
                if report_sections.get("executive_summary"):
                    with st.expander("Executive Summary", expanded=True):
                        st.write(report_sections["executive_summary"])
                        
                if report_sections.get("violation_summary"):
                    with st.expander("Violation Summary", expanded=True):
                        st.write(report_sections["violation_summary"])
                        
                if report_sections.get("risk_analysis"):
                    with st.expander("Risk Analysis"):
                        st.write(report_sections["risk_analysis"])
                        
                if report_sections.get("recommended_actions"):
                    with st.expander("Recommended Actions"):
                        st.write(report_sections["recommended_actions"])
                        
                if report_sections.get("affected_ingredients"):
                    with st.expander("Affected Ingredients"):
                        st.write(report_sections["affected_ingredients"])
                        
                if report_sections.get("applicable_regulations"):
                    with st.expander("Applicable Regulations"):
                        st.write(report_sections["applicable_regulations"])
                
                # --- Detail Table ---
                st.subheader("Detailed Screening Results")
                if screening_results:
                    df = pd.DataFrame(screening_results)
                    
                    # Exact Emoji Mapping
                    status_map = {
                        "RESTRICTED": "🔴 RESTRICTED",
                        "THRESHOLD_EXCEEDED": "🔴 THRESHOLD_EXCEEDED",
                        "ALLOWED": "🟢 ALLOWED",
                        "EXEMPTION_AVAILABLE": "🟢 EXEMPTION_AVAILABLE",
                        "NEEDS_REVIEW": "🟡 NEEDS_REVIEW"
                    }
                    
                    df["status"] = df["status"].apply(lambda x: status_map.get(x, x))
                    
                    # Select and rename columns for display
                    display_df = df[[
                        "component_name", "ingredient_name", "regulation_name", 
                        "measured_value", "threshold_value", "status", "confidence", "reasoning"
                    ]]
                    
                    display_df.columns = [
                        "Component", "Ingredient", "Regulation", 
                        "Measured Value", "Allowed Limit", "Status", "Confidence", "Reasoning"
                    ]
                    
                    st.dataframe(display_df, use_container_width=True, hide_index=True)
                else:
                    st.info("No detailed screening results found for this run.")

            elif json_res.status_code == 404:
                st.error("Report not found. The workflow run may not exist or did not complete successfully.")
            else:
                st.error(f"Failed to load report: {json_res.text}")
                
        except Exception as e:
            st.error(f"Connection error: {e}")
