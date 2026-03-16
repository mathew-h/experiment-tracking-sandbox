import streamlit as st
import smtplib
from email.message import EmailMessage
import os # Might be needed for env vars if not using secrets
from datetime import datetime

def send_issue_email(title, location, description):
    """Sends the issue report via email using credentials from st.secrets."""
    try:
        # --- Get Credentials from st.secrets --- 
        # Ensure you have a .streamlit/secrets.toml file with:
        # [email_credentials]
        # sender_email = "your_sender_email@example.com"
        # sender_password = "your_app_password_or_regular_password"
        # recipient_email = "recipient_email@example.com"
        # smtp_server = "smtp.example.com" # e.g., smtp.gmail.com
        # smtp_port = 587 # e.g., 587 for TLS
        
        sender = st.secrets["email_credentials"]["sender_email"]
        password = st.secrets["email_credentials"]["sender_password"]
        recipient = st.secrets["email_credentials"]["recipient_email"]
        smtp_server = st.secrets["email_credentials"]["smtp_server"]
        smtp_port = st.secrets["email_credentials"]["smtp_port"]

        # --- Create Email Message --- 
        msg = EmailMessage()
        msg['Subject'] = f"App Issue Report: {title}"
        msg['From'] = sender
        msg['To'] = recipient

        # Construct email body
        body = f"""
        An issue has been reported for the Experiment Tracking App:

        Title: {title}
        Page/Location: {location}
        Date/Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

        Description:
        --------------------
        {description}
        --------------------
        """
        msg.set_content(body)

        # --- Send Email --- 
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()  # Secure the connection
            server.login(sender, password)
            server.send_message(msg)
        return True

    except KeyError as e:
        st.error(f"Missing email credential in st.secrets: {e}. Please check your .streamlit/secrets.toml file.")
        return False
    except smtplib.SMTPAuthenticationError:
        st.error("Email authentication failed. Check sender email/password in st.secrets.")
        return False
    except Exception as e:
        st.error(f"Failed to send issue report email: {str(e)}")
        return False

def render_issue_submission_form():
    """Renders a form for users to submit issues or bugs."""
    st.subheader("Report an Issue")
    st.markdown("Found a bug or have a suggestion? Please let us know!")

    with st.form("issue_submission_form", clear_on_submit=True):
        issue_title = st.text_input(
            "Issue Title / Summary",
            placeholder="e.g., Cannot save sample with 0,0 coordinates",
            help="Provide a brief, descriptive title for the issue.",
            key="issue_title"
        )
        page_location = st.text_input(
            "Page / Location",
            placeholder="e.g., New Rock Sample page",
            help="Where in the application did you encounter the issue?",
            key="issue_location"
        )
        description = st.text_area(
            "Detailed Description",
            placeholder="Please describe the issue in detail. Include steps to reproduce if possible.",
            height=150,
            help="Provide as much detail as possible about the issue and how to reproduce it.",
            key="issue_description"
        )
        # Optional screenshot upload
        # uploaded_file = st.file_uploader(
        #     "Upload Screenshot (Optional)",
        #     type=['png', 'jpg', 'jpeg'],
        #     key="issue_screenshot"
        # )

        submitted = st.form_submit_button("Submit Issue Report")

        if submitted:
            # Basic validation
            if not issue_title or not description or not page_location:
                st.error("Please fill in the Title, Page/Location, and Description fields.")
            else:
                # --- Attempt to send email --- 
                email_sent = send_issue_email(
                    title=issue_title,
                    location=page_location,
                    description=description
                )
                # -----------------------------

                if email_sent:
                    st.success("Thank you for your feedback! Your issue report has been submitted via email.")
                # Error message is handled within send_issue_email

# Example usage (for testing this component directly)
# if __name__ == "__main__":
#     render_issue_submission_form() 