import streamlit as st

# Add CSS styles to align the "fetch" button at the bottom of the row
st.markdown(
    """
    <style>
    .row-widget.stHorizontal {
        display: flex;
        flex-direction: row;
        align-items: flex-end;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Create two columns with st.beta_columns
col1, col2 = st.columns([3, 1])  # Adjust the width ratio as per your requirement

# Add elements to the first column
name = col1.text_input("Enter Name")

# Add elements to the second column
btn = col2.button("Fetch")
    # Fetch button is clicked
    # Perform the desired action here, such as fetching data

# Rest of your Streamlit app code...
