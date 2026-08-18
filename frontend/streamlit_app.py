import streamlit as st

st.set_page_config(
    page_title="Product & Material Ingredient Screening Platform",
    page_icon="🌍",
    layout="wide"
)

st.title("Product & Material Ingredient Screening Platform")

st.markdown("""
Welcome to the AI-Powered Supply Chain Compliance Agent. 
This platform automates the extraction, screening, and regulatory validation of supplier documents (SDS, BOMs, FMDs) using advanced LangGraph orchestration and MCP external tooling.

### Available Modules:

👈 **Use the sidebar to navigate to the different modules:**

* **1. Dashboard**: High-level metrics, compliance alerts, and system health overview.
* **2. Product Screening**: Upload supplier documents and trigger the AI compliance pipeline.
* **3. Screening Results**: Deep-dive into individual product screening breakdowns and part-level compliance.
* **4. Compliance Reports**: Access generated PDF/Markdown executive summaries and compliance certificates.
* **5. Review Queue**: Human-in-the-loop task queue for subjective rule judgments and low-confidence extractions.
* **6. Settings**: Configure regulatory thresholds, API keys, and notification preferences.

*Note: Some pages are currently under construction as we roll out Phase 5 features.*
""")
