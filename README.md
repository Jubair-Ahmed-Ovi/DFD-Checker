# DFD Image to JSON Converter — Gemini Edition

This version uses the **Google Gemini API** instead of OpenAI. It accepts DFD images/PDFs, sends the normalized image to Gemini Vision, requests structured JSON using the fixed DFD JSON schema, validates the result locally, and displays it in the browser.

Google's current GenAI Python SDK supports multimodal image input and structured JSON output using `response_mime_type="application/json"` plus a JSON/Pydantic schema.

## Requirements

- Python 3.10+
- A Gemini API key
- Internet connection

## Windows PowerShell setup

Open PowerShell in this folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
Copy-Item .env.example .env
```

Open `.env` and put your Gemini key:

```env
GEMINI_API_KEY=your_real_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash
MAX_FILE_SIZE_MB=20
```

Keep `.env` private. Never put the Gemini API key in frontend JavaScript.

## Run

Use this command on Windows:

```powershell
python -m uvicorn backend.main:app --reload
```

Then open:

```text
http://127.0.0.1:8000
```

## Supported input

PNG, JPG, JPEG, WEBP, BMP, TIFF, GIF, SVG and PDF.

PDF/SVG/image files are normalized to PNG before the Gemini request. The current starter processes the first PDF page.

## How it works

```text
Upload
  -> normalize image
  -> Gemini Vision
  -> structured DFD JSON
  -> local JSON/schema validation
  -> edit/copy/download
```

## Important

The JSON schema is in:

```text
backend/schemas/dfd_schema.json
```

Keep that schema unchanged if it is your fixed format.
