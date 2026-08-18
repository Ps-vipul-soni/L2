import requests
import streamlit as st

API_BASE = "http://127.0.0.1:8000"

st.set_page_config(page_title="Product Screening", layout="wide")
st.title("Product Screening")
st.markdown("Select an existing product portfolio and upload a supplier document (SDS, BOM, or FMD) to trigger the AI compliance pipeline.")

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

# Format product dropdown: Name (SKU)
product_options = {f"{p['name']} ({p.get('sku', 'N/A')})": p["id"] for p in products}

with st.container(border=True):
    selected_product_name = st.selectbox("1. Select Product Portfolio", options=list(product_options.keys()))
    product_id = product_options[selected_product_name]
    
    uploaded_files = st.file_uploader("2. Upload Supplier Document(s)", type=["pdf", "csv", "xls", "xlsx", "xml"], accept_multiple_files=True)
    
    if st.button("Trigger AI Pipeline", type="primary", disabled=not uploaded_files):
        
        # 1. Upload Documents
        document_ids = []
        with st.spinner("Uploading documents..."):
            try:
                for uploaded_file in uploaded_files:
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                    data = {"product_id": product_id}
                    upload_res = requests.post(f"{API_BASE}/documents/upload", files=files, data=data)
                    
                    if upload_res.status_code == 200:
                        document_ids.append(upload_res.json().get("document_id"))
                    else:
                        st.error(f"Upload failed for {uploaded_file.name}: {upload_res.json().get('detail', upload_res.text)}")
            except Exception as e:
                st.error(f"Connection error during upload: {e}")

        # 2. Trigger Pipeline (Blocking)
        if document_ids and len(document_ids) == len(uploaded_files):
            workflow_run_id = None
            with st.spinner("Running pipeline... Please wait as the AI analyzes the documents and screens for compliance."):
                try:
                    trigger_res = requests.post(
                        f"{API_BASE}/pipeline/trigger", 
                        json={"document_ids": document_ids}
                    )
                    if trigger_res.status_code == 200:
                        workflow_run_id = trigger_res.json().get("workflow_run_id")
                    else:
                        st.error(f"Pipeline failed: {trigger_res.json().get('detail', trigger_res.text)}")
                except Exception as e:
                    st.error(f"Connection error during pipeline trigger: {e}")

            # 3. Retroactive Summary Check
            if workflow_run_id:
                st.subheader("Pipeline Results")
                try:
                    summary_res = requests.get(f"{API_BASE}/pipeline/workflow-runs/{workflow_run_id}/summary")
                    if summary_res.status_code == 200:
                        summary = summary_res.json()
                        status = summary["status"]
                        overall_status = summary["overall_status"]
                        stages = summary["inferred_stages"]
                        reasons = summary["review_queue_reasons"]
                        
                        # Render Stages
                        st.markdown("#### Execution Stages")
                        for stage_name, stage_val in stages.items():
                            if stage_val is True:
                                st.write(f"✅ {stage_name}")
                            elif stage_val == "Unknown":
                                st.write(f"❓ {stage_name} (Unknown/Unverified)")
                            else:
                                st.write(f"❌ {stage_name}")
                                
                        st.divider()
                        
                        def render_pipeline_stages(run_id: str):
                            st.write("### Pipeline Stages Details")
                            try:
                                res = requests.get(f"{API_BASE}/pipeline/{run_id}/stages")
                                if res.status_code == 200:
                                    stages = res.json()
                                    
                                    # 1. Document Understanding
                                    docs = stages.get("document_understanding", [])
                                    for doc in docs:
                                        with st.expander(f"📄 Document Understanding: {doc['filename']}"):
                                            st.write(f"**Type:** {doc['doc_type']}")
                                            st.write(f"**Confidence:** {doc['extraction_confidence']}")
                                            if doc.get("extraction_notes"):
                                                st.write("**Notes:**")
                                                st.info(doc["extraction_notes"])
                                                
                                    # 2. Ingredient Extraction
                                    ing_ext = stages.get("ingredient_extraction")
                                    if ing_ext:
                                        with st.expander("🧪 Ingredient Extraction"):
                                            for item in ing_ext:
                                                st.write(f"- **{item['canonical_name']}** (in {item['component_name']}): {item['concentration_value']} {item['concentration_unit']}")
                                                
                                    # 3. Chemical Normalization
                                    chem_norm = stages.get("chemical_normalization")
                                    if chem_norm:
                                        with st.expander("🧬 Chemical Normalization"):
                                            for item in chem_norm:
                                                aliases = ", ".join(item['aliases']) if item['aliases'] else "None"
                                                st.write(f"- **{item['canonical_name']}** (CAS: {item['cas_number']}) — Aliases: {aliases}")
                                                
                                    # 4. Regulation Planning
                                    reg_plan = stages.get("regulation_planning")
                                    if reg_plan:
                                        with st.expander("⚖️ Regulation Planning"):
                                            applicable = [r for r in reg_plan if r["applies"]]
                                            not_applicable = [r for r in reg_plan if not r["applies"]]
                                            
                                            if applicable:
                                                st.markdown("#### 🟢 Applicable")
                                                for r in applicable:
                                                    st.markdown(f"**{r['regulation_code']}**<br/>*Reason:* {r['reason']}", unsafe_allow_html=True)
                                                    st.markdown("---")
                                                    
                                            if not_applicable:
                                                st.markdown("#### 🔴 Not Applicable")
                                                for r in not_applicable:
                                                    st.markdown(f"**{r['regulation_code']}**<br/>*Reason:* {r['reason']}", unsafe_allow_html=True)
                                                    st.markdown("---")
                                                    
                            except Exception as e:
                                st.error(f"Failed to fetch pipeline stages details: {e}")

                        # Final Outcome
                        if status == "COMPLETED":
                            if overall_status == "PASS":
                                st.success(f"Outcome: {overall_status}")
                            elif overall_status == "WARNING":
                                st.warning(f"Outcome: {overall_status}")
                            else:
                                st.error(f"Outcome: {overall_status}")
                                
                            st.session_state.workflow_run_id = workflow_run_id
                            st.info("The Compliance Report has been successfully generated. Please navigate to **Compliance Reports** in the sidebar to view it.")
                            render_pipeline_stages(workflow_run_id)
                            
                        elif status == "PARTIAL":
                            st.warning("⚠️ Pipeline halted for manual review.")
                            if reasons:
                                st.write("**Reasons:**")
                                for r in reasons:
                                    st.write(f"- {r}")
                            st.info("Please navigate to the **Review Queue** in the sidebar to resolve these items.")
                            render_pipeline_stages(workflow_run_id)
                        
                        elif status == "FAILED":
                            st.error("❌ The pipeline encountered a fatal error and did not complete.")
                            
                    else:
                        st.error("Failed to fetch pipeline summary.")
                except Exception as e:
                    st.error(f"Connection error fetching summary: {e}")
