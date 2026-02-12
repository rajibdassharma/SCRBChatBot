import streamlit as st
import mysql.connector

import src.utils.database_config as dbconfig
from src.utils.constants import AI_DOMAIN_OPTIONS, AI_ROLE_OPTIONS

if "db_info" not in st.session_state:
    st.session_state.db_info = {}
if "user_info" not in st.session_state:
    st.session_state.user_info = {}


def mainusrmgr():
    # Create an empty container
    placeholder = st.empty()
    with placeholder.form('login_form'):
        
        show_msg=""

        conn, c = initialize_database()

        st.markdown("<h1 style='text-align: center;'>Your AI Assistant - 1.0</h1>", unsafe_allow_html=True)
        st.markdown("<h2 style='font-size: 20px;'>User Administration</h2>", unsafe_allow_html=True)
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
            c.execute("SELECT name, password, domain, role FROM user WHERE email=%s", (email,))
            user = c.fetchone()
            user_info = {}
            if user:
                user_info = {'email':email, 'name': user[0], 'password':user[1],'domain':user[2],'role':user[3]}
            return user_info

        name_val="" 
        pwd_val="" 
        domain_val="Select"
        role_val="Select"
        if (st.session_state.trysave=="Y"):
            name_val = st.session_state.user_info['name']
            pwd_val = st.session_state.user_info['password']
            domain_val = st.session_state.user_info['domain']
            role_val = st.session_state.user_info['role']
            st.session_state["trysave"]=""
        # Fetch details
        #if fetch_button_clicked:
        elif email:
            user_info = fetch_details(email)
            if len(user_info) > 0:
                name_val = user_info['name']
                pwd_val = user_info['password']
                domain_val = user_info['domain']
                role_val = user_info['role']
                show_msg="User details fetched successfully."
            else:
                #st.write(st.session_state.trysave)
                #if (st.session_state.trysave != "Y"):
                #st.write("i m aheree")
                st.session_state.user_info["name"]=""
                st.session_state.user_info["password"]=""
                st.session_state.user_info["domain"]="Select"
                st.session_state.user_info["role"]="Select"
                show_msg="User not found."

        col3, col4 = st.columns(2)
        name = col3.text_input("Name", value=name_val,key="name")
        password = col4.text_input("Password", type="password", value=pwd_val,key="password")

        col5, col8, col6 = st.columns([3,3,2.5])
        domain = col5.selectbox("Domain", key="domain", options=AI_DOMAIN_OPTIONS, index=AI_DOMAIN_OPTIONS.index(domain_val))
        role = col8.selectbox("Role", key="role", options=AI_ROLE_OPTIONS, index=AI_ROLE_OPTIONS.index(role_val))
        
        def saveme():
            st.session_state["trysave"] = "Y"
            
        with col6:
            html_code = f'<div style="line-height: {1.8};">&nbsp;</div>'
            st.write(html_code, unsafe_allow_html=True)
            save_button_clicked = st.form_submit_button('Save', on_click=saveme) 
        

        # Function to insert or update user details
        def save_details(email, name, password, domain, role):
            c.execute("SELECT email, name, domain, role FROM user WHERE email=%s", (email,))
            if c.fetchone():
                c.execute("UPDATE user SET password=%s, name=%s, domain=%s, role=%s, WHERE email=%s",
                      (password, name, domain, role, email))
            else:
                c.execute("INSERT INTO user (email, name, password, domain, role) VALUES (%s, %s, %s, %s, %s)",
                      (email, name, password, domain, role))
            conn.commit()
            return "User details saved successfully."

        
        # Save details
        if save_button_clicked:
            if email and password and name and domain and role:
                show_msg=save_details(email, name, password, domain, role)
            else:
                show_msg="Please fill in all the fields."

        if show_msg:
            st.info(show_msg)
        # Close the database connection
        conn.close()

def initialize_database():
        
        hostname = dbconfig.HOSTNAME
        dbname = dbconfig.DATABASE
        userid = dbconfig.USERID
        password = dbconfig.PASSWORD
        
        db_info = {'hostname':hostname,'dbname':dbname,'userid':userid,'password':password}
        
        # Step 1: Connect to the Database
        conn = mysql.connector.connect(host=hostname, user=userid, password=password)
        c = conn.cursor()

        # Step 2: Delete the database if it exists already.
        # This is only for the Testing phase to avoid using command line
        dbDeleteStr = "DROP DATABASE IF EXISTS " + dbname
        c.execute(dbDeleteStr)
        print ("Database " + dbname + " deleted successfully.")
        
        # Step 3: Create the database
        dbCreateStr = "CREATE DATABASE IF NOT EXISTS " + dbname
        c.execute(dbCreateStr)
        print ("Database " + dbname + " created successfully.")

        # Step 4: Connect to the Database
        conn = mysql.connector.connect(host=hostname, database=dbname, user=userid, password=password)
        c = conn.cursor()

        # Step 5: Create the USER table if it doesn't exist
        userTableCreateStr = '''CREATE TABLE IF NOT EXISTS ''' + dbconfig.USERTABLE + \
                            '''(email VARCHAR(80) PRIMARY KEY,
                                name VARCHAR(80),
                                password VARCHAR(45),
                                role VARCHAR(45),
                                domain VARCHAR(45))'''
        print(userTableCreateStr)
        c.execute(userTableCreateStr)

        # Step 6: Add the default users
        for user in dbconfig.default_users:
            userCreateStr = '''INSERT INTO ''' + dbconfig.USERTABLE + \
            '''(email, name, password, role, domain) VALUES (%s, %s, %s, %s, %s)'''
            c.execute(userCreateStr, (user['email'], user['name'], user['password'], user['role'], user['domain']))
            print("New User Created...")
        
        conn.commit()
        return conn, c

def autheticate_user(userid, password):
        
        #hostname = dbconfig.HOSTNAME
        #dbname = dbconfig.DATABASE
        #dbuserid = dbconfig.USERID
        #dbpassword = dbconfig.PASSWORD
        #user_info = {}

        #conn = mysql.connector.connect(host=hostname, database=dbname, user=dbuserid, password=dbpassword)
        #c = conn.cursor()
        #c.execute("SELECT name, password, domain, role FROM user WHERE email=%s", (userid,))
        #user = c.fetchone()
        #if user:

        #    user_info = {'email':userid, 'name': user[0], 'password':user[1],'domain':user[2],'role':user[3]}
        
        user_info = {}
        user_info = {'email': userid, 'name': 'Test User','password': password,'domain':'Sales','role':'Admin'}
        return user_info

if __name__ == '__main__':
    if 'trysave' not in st.session_state:
        st.session_state["trysave"]=""
    #initialize_database()
    mainusrmgr()
