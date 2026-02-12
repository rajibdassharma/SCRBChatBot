from pathlib import Path
import streamlit as st
from .helpers import render_svg


def show_info(icon: Path) -> None:
    st.divider()

    st.write("This is a demo of the **You Ask I Answer** app.\n" 
             "The app is based on the **Streamlit** framework and\n" 
             "the **OpenAI** API. The app is a work in progress.\n" 
             "Please report any bugs or issues to the developer.")

    st.divider()
    