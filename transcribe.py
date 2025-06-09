import gspread
import openai
import os
import re
import io
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import pickle
import traceback
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
# Load environment variables from .env file if it exists
if os.path.exists('.env'):
    load_dotenv()

# --- UPDATE THESE VALUES ---
# The ID of your Google Sheet (from the URL)
SHEET_ID = os.getenv("SHEET_ID", "1Z8E_e6tB8jxffKrZM0LkaVxLJfAueJOk53uILL1CjK8")
# The name of the sheet/tab you want to process
SHEET_NAME = os.getenv("SHEET_NAME", "Sheet1")
# The column numbers for your data (A=1, B=2, C=3, etc.)
ANSWER_COLUMN_MAP = {
    12: 4,   # L (Audio 1) -> D (Answer 1)
    13: 6,   # M (Audio 2) -> F (Answer 2)
    14: 8,   # N (Audio 3) -> H (Answer 3)
    15: 10,  # O (Audio 4) -> J (Answer 4)
}
# Email configuration
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
RECIPIENT_EMAILS = [email.strip() for email in os.getenv("RECIPIENT_EMAIL", "").split(",") if email.strip()]
# Progress tracking file
PROGRESS_FILE = os.getenv("PROGRESS_FILE", "transcription_progress.json")
# --- END OF CONFIGURATION ---

# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/spreadsheets',
          'https://www.googleapis.com/auth/drive']

def authenticate():
    """Handles authentication for Google and OpenAI services."""
    try:
        creds = None
        # The file token.pickle stores the user's access and refresh tokens
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
        
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # For Railway deployment, we'll use service account credentials
                if os.getenv("GOOGLE_CREDENTIALS"):
                    creds = Credentials.from_authorized_user_info(
                        json.loads(os.getenv("GOOGLE_CREDENTIALS")),
                        SCOPES
                    )
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        'credentials.json', SCOPES)
                    creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)
        
        # Initialize API clients
        gspread_client = gspread.authorize(creds)
        drive_service = build('drive', 'v3', credentials=creds)
        
        # OpenAI API Key
        openai.api_key = os.getenv("OPENAI_API_KEY")
        if not openai.api_key:
            raise ValueError("OpenAI API key not found. Please set it in the environment variables.")
            
        return gspread_client, drive_service
    except Exception as e:
        logger.error(f"An error occurred during authentication: {e}")
        return None, None

def load_progress():
    """Load the last processed row number from the progress file."""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            return json.load(f)
    return {"last_processed_row": 1}

def save_progress(last_row):
    """Save the last processed row number to the progress file."""
    with open(PROGRESS_FILE, 'w') as f:
        json.dump({"last_processed_row": last_row}, f)

def send_summary_email(stats):
    """Send a summary email about the transcription process."""
    if not all([SMTP_SERVER, SMTP_PORT, SENDER_EMAIL, SENDER_PASSWORD]) or not RECIPIENT_EMAILS:
        print("Email configuration not found. Skipping email summary.")
        return

    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = ", ".join(RECIPIENT_EMAILS)
    msg['Subject'] = "Transcription Process Summary"

    body = f"""
    Transcription Process Summary:
    
    Total files processed: {stats['total_processed']}
    Successfully transcribed: {stats['successful']}
    Failed transcriptions: {stats['failed']}
    
    Errors encountered:
    {stats['errors']}
    
    Last processed row: {stats['last_row']}
    """

    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("Summary email sent successfully.")
    except Exception as e:
        print(f"Failed to send summary email: {e}")

def main():
    """Main function to run the transcription process."""
    logger.info("Starting transcription process")
    
    gspread_client, drive_service = authenticate()
    if not gspread_client or not drive_service:
        logger.error("Failed to authenticate")
        return

    # Initialize statistics
    stats = {
        "total_processed": 0,
        "successful": 0,
        "failed": 0,
        "errors": [],
        "last_row": 0
    }

    try:
        logger.info(f"Attempting to open Google Sheet with ID: {SHEET_ID}")
        sheet_file = gspread_client.open_by_key(SHEET_ID)
        logger.info(f"Successfully opened Google Sheet. Attempting to open worksheet: {SHEET_NAME}")
        sheet = sheet_file.worksheet(SHEET_NAME)
        logger.info(f"Successfully opened worksheet: {SHEET_NAME}. Fetching all rows...")
        all_rows = sheet.get_all_values()
        logger.info("Successfully connected to Google Sheet.")
    except Exception as e:
        error_msg = f"Error accessing Google Sheet: {e!r}"
        logger.error(error_msg)
        stats["errors"].append(error_msg)
        send_summary_email(stats)
        return

    # Load the last processed row
    progress = load_progress()
    start_row = progress["last_processed_row"]
    logger.info(f"Starting from row {start_row}")

    # Loop through each row in the sheet, skipping the header and already processed rows
    for row_index, row in enumerate(all_rows[start_row:], start=start_row + 1):
        stats["last_row"] = row_index
        for audio_col, answer_col in ANSWER_COLUMN_MAP.items():
            audio_col_index = audio_col - 1
            answer_col_index = answer_col - 1

            audio_cell = row[audio_col_index] if len(row) > audio_col_index else ""
            answer_cell = row[answer_col_index] if len(row) > answer_col_index else ""

            # Fetch the formula for the audio cell
            formula = sheet.cell(row_index, audio_col, value_render_option='FORMULA').value
            logger.debug(f"Row {row_index}, Audio Col {audio_col} ({audio_col_index}): formula='{formula}' | display='{audio_cell}' | Answer Col {answer_col} ({answer_col_index}): '{answer_cell}'")

            if (formula and "HYPERLINK" in formula and (answer_cell == "")):
                stats["total_processed"] += 1
                logger.info(f"Found pending transcription in row {row_index}, column {audio_col}...")
                try:
                    # 1. Extract File ID from formula
                    match = re.search(r'd/([a-zA-Z0-9_-]+)/', formula)
                    if not match:
                        logger.warning(f"Could not parse File ID from cell formula.")
                        stats["failed"] += 1
                        stats["errors"].append(f"Row {row_index}: Could not parse File ID from cell formula")
                        continue
                    file_id = match.group(1)

                    # 2. Download file from Drive
                    logger.info(f"Downloading file ID: {file_id}")
                    request = drive_service.files().get_media(fileId=file_id)
                    file_content = io.BytesIO(request.execute())
                    file_content.name = "audio.webm" # Whisper API needs a file name

                    # 3. Transcribe with Whisper
                    logger.info("Sending to Whisper for transcription...")
                    transcript = openai.audio.transcriptions.create(
                        model="whisper-1",
                        file=file_content
                    )
                    transcribed_text = transcript.text
                    logger.info(f"Success! Transcription: '{transcribed_text[:50]}...'")

                    # 4. Update the Sheet
                    sheet.update_cell(row_index, answer_col, transcribed_text)
                    logger.info(f"Updated sheet at row {row_index}, column {answer_col}.")
                    stats["successful"] += 1
                except Exception as e:
                    error_msg = f"Row {row_index}: {str(e)}"
                    logger.error(f"Error: {error_msg}")
                    stats["failed"] += 1
                    stats["errors"].append(error_msg)

        # Save progress after each row
        save_progress(row_index)

    logger.info("Transcription process finished.")
    send_summary_email(stats)

if __name__ == "__main__":
    main() 