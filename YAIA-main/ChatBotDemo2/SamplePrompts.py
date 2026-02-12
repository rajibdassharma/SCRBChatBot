import pandas as pd
import streamlit as st

def show_prompts(domain):
    
    st.markdown(f"<h2 style='text-align: center;'>Sample prompts for {domain}</h2>", unsafe_allow_html=True)
    path = "/Users/rajibdassharma/Python/data/YAIASamplePrompts.xlsx"
    df_domain = pd.read_excel(path,sheet_name=domain)

    st.write(df_domain)