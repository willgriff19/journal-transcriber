# Journal Transcriber

An automated system that transcribes audio journal entries from Google Drive to a Google Sheet using OpenAI's Whisper API.

## Features

- Automatically transcribes audio files from Google Drive
- Updates transcriptions in a Google Sheet
- Tracks progress to avoid re-processing entries
- Sends email summaries of transcription results
- Runs on a schedule using Railway

## Setup

### Prerequisites

- Python 3.8+
- Google Cloud Project with Drive and Sheets APIs enabled
- OpenAI API key
- Gmail account for sending notifications

### Local Development

1. Clone the repository:
```bash
git clone <your-repo-url>
cd journal-transcriber
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables in `.env`:
```
SHEET_ID=your_sheet_id
SHEET_NAME=Sheet1
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SENDER_EMAIL=your_email@gmail.com
SENDER_PASSWORD=your_app_password
RECIPIENT_EMAIL=email1@example.com, email2@example.com
OPENAI_API_KEY=your_openai_api_key
```

5. Set up Google credentials:
   - Download your Google Cloud credentials as `credentials.json`
   - Place it in the project root directory

### Railway Deployment

1. Create a new project on Railway
2. Connect your GitHub repository
3. Set up the following environment variables in Railway:
   - All variables from the `.env` file
   - `GOOGLE_CREDENTIALS`: Your Google service account credentials as a JSON string

## Usage

### Local Development

Run the script:
```bash
python transcribe.py
```

### Railway Deployment

The script will automatically run every 6 hours on Railway. You can adjust the schedule in `railway.json`.

## Configuration

- `SHEET_ID`: Your Google Sheet ID
- `SHEET_NAME`: The name of the sheet to process
- `ANSWER_COLUMN_MAP`: Maps audio columns to answer columns
- Email settings in environment variables
- Cron schedule in `railway.json`

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request 