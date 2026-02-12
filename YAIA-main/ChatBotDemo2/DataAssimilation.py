import tempfile
import os
from pathlib import Path
from random import randrange

import streamlit as st
from streamlit_option_menu import option_menu
from src.styles.menu_styles import FOOTER_STYLES, HEADER_STYLES
from src.utils.conversation import get_user_input, show_chat_buttons, show_conversation
from src.utils.footer import show_info
from src.utils.helpers import get_files_in_dir, get_random_img
from src.utils.lang import en

from WebCrawler4 import scrape_url
from UploadFiles import upload_files, upload_process_all_files

# Storing The Context
if "locale" not in st.session_state:
    st.session_state.locale = en
if "filesuploaded" not in st.session_state:
    st.session_state.filesuploaded = 0
if "data" not in st.session_state:
    st.session_state["data"] = []
    data = []
if "dataLoaded" not in st.session_state:
    st.session_state.dataLoaded = False


def extract_and_upload(url, webcrawl_path, otherfiles_path):
    numfiles = 0
    print("Going to scrape the URL....")
    scrape_url(url, webcrawl_path)
    print("URL scraping done....going to upload files....")
    all_files_path = [webcrawl_path, otherfiles_path]
    numfiles = upload_process_all_files(all_files_path)
    #st.session_state.dataLoaded = True
    return numfiles

def data_assmltn_form():
    #placeholder = st.empty()
    #print("In form")
    numfiles = 0
  
    user_input_container = st.empty()
    with user_input_container.form('data_assimilation_form'):
        #with st.form(key='data_upload_form', clear_on_submit=True):
        st.markdown("<h1 style='text-align: center;'>Your AI Assistant - 1.0</h1>", unsafe_allow_html=True)
        st.markdown("<h2 style='text-align: center;'>Data Assimilation</h2>", unsafe_allow_html=True)
        
        url             = st.text_input("URL for web crawling")
        webcrawl_path   = st.text_input("Web Crawl Data storage Location")
        otherfiles_path = st.text_input("Other Files storage Location")

        print("url : " + url + " Web Crawl Path : " + webcrawl_path + "Other Files Path : " +  otherfiles_path)

        extract_button  = st.form_submit_button(label='Extract and Upload Files')

        if extract_button:
            
            if url == "" or webcrawl_path == "" or otherfiles_path == "":
                st.error("Please enter all the details")
            else:
                print("In DataAssimilation -> Going to extract and upload files....")
                numfiles = extract_and_upload(url, webcrawl_path, otherfiles_path)
                print("In DataAssimilation -> No of files uploaded: " + str(numfiles))
                st.session_state.bulk_upload = False
                user_input_container.empty() # This must be added, otherwise the form will be displayed again
        else:
            pass
    
    return numfiles

if __name__ == '__main__':
     print("In main")
     data_assmltn_form()
