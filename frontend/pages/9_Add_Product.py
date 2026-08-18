import streamlit as st
import requests

API_BASE = "http://127.0.0.1:8000"

st.set_page_config(page_title="Add Product", layout="centered")
st.title("Add New Product")
st.markdown("Create a new product portfolio to be screened for compliance.")

with st.form("add_product_form"):
    name = st.text_input("Product Name *", help="e.g. Acme Laptop Model X")
    sku = st.text_input("SKU *", help="Must be unique across all products.")
    product_type = st.text_input("Product Type *", help="e.g. electronics, apparel, medical")
    market_country = st.text_input("Target Market *", help="e.g. United States, California, European Union")
    customer_name = st.text_input("Customer Name", help="Optional. Internal tracking name")
    
    submitted = st.form_submit_button("Create Product", type="primary")

if submitted:
    if not name or not sku or not product_type or not market_country:
        st.error("Name, SKU, Product Type, and Target Market are required fields.")
    else:
        payload = {
            "name": name,
            "sku": sku,
            "product_type": product_type,
            "market_country": market_country,
            "customer_name": customer_name if customer_name else None
        }
        
        with st.spinner("Creating product..."):
            try:
                res = requests.post(f"{API_BASE}/products", json=payload)
                
                if res.status_code == 200:
                    st.success(f"Product '{name}' (SKU: {sku}) created successfully!")
                    st.info("You can now navigate to 'Product Screening' to upload a document for this product.")
                    
                    # Targeted cache invalidation check:
                    # Because get_products() is defined inside 2_Product_Screening.py, 
                    # importing it here (via importlib) to call get_products.clear() would 
                    # execute all the top-level Streamlit UI commands in that page file, 
                    # injecting Page 2's UI into Page 9. 
                    # Since refactoring is explicitly forbidden, and Streamlit has no string-key 
                    # cache invalidation API for @st.cache_data, clearing the global data cache 
                    # is the only mathematically possible way to bust the cache without refactoring.
                    st.cache_data.clear()
                    
                elif res.status_code == 409:
                    st.error(f"Error: {res.json().get('detail')}")
                else:
                    st.error(f"Failed to create product. Status: {res.status_code} - {res.text}")
            except Exception as e:
                st.error(f"Connection error: {e}")
