import streamlit as st
from pathlib import Path
from src.utils.constants import AI_DOMAIN_OPTIONS, AI_ROLE_OPTIONS, AI_MODEL_OPTIONS, AI_IMAGE_MODEL_OPTIONS
from UserManager import autheticate_user


def main_login():

    # Create an empty container
    placeholder = st.empty()

    '''
    actual_email = "email"
    actual_password = "password"
    domain = "domain"
    '''

    login_info = {}

    with placeholder.form('login_form'):
        st.markdown("<h1 style='text-align: center;'>Your AI Assistant - 1.0</h1>", unsafe_allow_html=True)
        st.markdown("<h2 style='text-align: center;'>Enter your Login Credentials & Domain</h1>", unsafe_allow_html=True)
        # Creating columns to organize the form
        col1, col2 = st.columns(2)
        with col1:
            email = st.text_input('UserID/Email')
            password = st.text_input('Password', type="password")
            col1.selectbox(label=st.session_state.locale.select_placeholder1, key="text_model", options=AI_MODEL_OPTIONS)
        with col2:
            domain = st.selectbox(label='Please select your Domain',options=AI_DOMAIN_OPTIONS,index=0)
            col2.selectbox(label=st.session_state.locale.select_placeholder2, key="role",options=AI_ROLE_OPTIONS)
            image_model = col2.selectbox(label=st.session_state.locale.select_placeholder3, key="image_model", options=AI_IMAGE_MODEL_OPTIONS)

        c1, c2 = st.columns(2)
        with c1, c2:
            input_kind = c1.radio(
                label="Bulk Upload Files (Only for Admin)",
                options=("Yes", "No"),
                horizontal=True,
            )
       
        if input_kind == "Yes":
            st.session_state.bulk_upload = True
        elif input_kind == "No":
            st.session_state.bulk_upload = False

        submit_button = st.form_submit_button('Submit')

        #check the email and password against the one stored in the database

        if submit_button:
            user_info = autheticate_user(email, password)
            if len(user_info) > 0:
                # If the form is submitted and the email and password are correct,
                # clear the form/container
                login_info.update({'email':email,'password':password,'domain':domain, 'image_model':image_model})
                st.session_state.login_info = login_info
                st.session_state.user_info = user_info
                st.session_state.login_success = True
                placeholder.empty() # This must be added, otherwise the form will be displayed again
                #st.success("Login successful")
                return st.session_state.login_success
            else:
                st.error("Login failed")
        else:
            pass
    return st.session_state.login_success
    
