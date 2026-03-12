import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import config

def send_email(subject, html_body):
    """
    Sends an email using the configuration in config.py
    """
    if not config.SENDER_EMAIL or not config.SENDER_PASSWORD:
        print("Error: Email credentials not set in environment variables.")
        return False
        
    msg = MIMEMultipart()
    msg['From'] = config.SENDER_EMAIL
    msg['To'] = config.RECIPIENT_EMAIL
    msg['Subject'] = subject
    
    msg.attach(MIMEText(html_body, 'html'))
    
    try:
        print(f"Connecting to {config.SMTP_SERVER}...")
        server = smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT)
        server.starttls()
        
        print(f"Logging in as {config.SENDER_EMAIL}...")
        server.login(config.SENDER_EMAIL, config.SENDER_PASSWORD)
        
        print(f"Sending email to {config.RECIPIENT_EMAIL}...")
        server.send_message(msg)
        server.quit()
        
        print("Email sent successfully!")
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False
