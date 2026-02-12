import streamlit as st
import mysql.connector

def mainusrmgr():
    # Create an empty container
    placeholder = st.empty()
    with placeholder.form('login_form'):
        
        show_msg=""
        conn = mysql.connector.connect(host="localhost", user="root", password="websabda",database="yaia")
        c = conn.cursor()
        # Create a table if it doesn't exist
        c.execute('''CREATE TABLE IF NOT EXISTS user
             (email VARCHAR(80) PRIMARY KEY,
              name VARCHAR(80),
              password VARCHAR(45),
              domain VARCHAR(45))''')


        st.markdown("<h3 style='font-size: 20px;'>User Administration</h3>", unsafe_allow_html=True)
        st.markdown("""    <style>    .stButton button {height: 40px;  } </style>""",    unsafe_allow_html=True)
        
        col1, col7, col2 = st.columns([3,0.5,2.5])
        email = col1.text_input("User ID/Email",key="email")
        col7.empty()
        with col2:
            html_code = f'<div style="line-height: {1.8};">&nbsp;</div>'
            st.write(html_code, unsafe_allow_html=True)
            #st.write("")    
            fetch_button_clicked = st.form_submit_button('Fetch') 
        # Function to fetch user details
        def fetch_details(email):
            c.execute("SELECT * FROM user WHERE email=%s", (email,))
            user = c.fetchone()
            return user

        name_val="" 
        pwd_val="" 
        domain_val="Select" 
        if (st.session_state.trysave=="Y"):
            name_val=st.session_state.name
            pwd_val=st.session_state.password
            domain_val=st.session_state.domain
            st.session_state["trysave"]=""
        # Fetch details
        #if fetch_button_clicked:
        elif email:
            user = fetch_details(email)
            if user:
                name_val, pwd_val, domain_val = user[1], user[2], user[3]
                show_msg="User details fetched successfully."
            else:
                #st.write(st.session_state.trysave)
                #if (st.session_state.trysave != "Y"):
                #st.write("i m aheree")
                show_msg="User not found."
                st.session_state["name"]=""
                st.session_state["password"]=""
                st.session_state["domain"]="Select"
                    
    
        col3, col4 = st.columns(2)
        name = col3.text_input("Name", value=name_val,key="name")
        password = col4.text_input("Password", type="password", value=pwd_val,key="password")

        col5, col8, col6 = st.columns([3,0.5,2.5])
        col8.empty()
        domain = col5.selectbox("Domain", key="domain", options=["Select", "HR", "Finance", "Education","Sales","Marketing"], index=["Select", "HR", "Finance", "Education","Sales","Marketing"].index(domain_val))
        
        def saveme():
            st.session_state["trysave"] = "Y"
            
            

        with col6:
            html_code = f'<div style="line-height: {1.8};">&nbsp;</div>'
            st.write(html_code, unsafe_allow_html=True)
            save_button_clicked = st.form_submit_button('Save', on_click=saveme) 
        
   

        # Function to insert or update user details
        def save_details(email, name, password, domain):
            c.execute("SELECT * FROM user WHERE email=%s", (email,))
            if c.fetchone():
                c.execute("UPDATE user SET password=%s, name=%s, domain=%s WHERE email=%s",
                      (password, name, domain, email))
            else:
                c.execute("INSERT INTO user (email, name, password, domain) VALUES (%s, %s, %s, %s)",
                      (email, name, password, domain))
            conn.commit()
            return "User details saved successfully."

        
        # Save details
        if save_button_clicked:
            if email and password and name and domain:
                show_msg=save_details(email, name, password, domain)
            else:
                show_msg="Please fill in all the fields."

        if show_msg:
            st.info(show_msg)
        # Close the database connection
        conn.close()


if __name__ == '__main__':
    if 'trysave' not in st.session_state:
        st.session_state["trysave"]=""
    mainusrmgr()
