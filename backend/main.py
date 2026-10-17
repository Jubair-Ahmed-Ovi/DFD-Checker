import os, json, uuid
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from .services.image_processor import convert_to_png_bytes
from .services.ai_service import extract_dfd
from .services.json_validator import validate_dfd
from .services.dfd_rules import audit_dfd

BASE = Path(__file__).resolve().parents[1]
UPLOADS = BASE / "backend" / "uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)
load_dotenv(BASE / ".env")

app = FastAPI(title="DFD Image to JSON Converter", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

ALLOWED = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif", ".svg", ".pdf"}
MAX_MB = int(os.getenv("MAX_FILE_SIZE_MB", "20"))

@app.get("/api/health")
def health():
    return {"status": "ok"}

@app.post("/api/convert")
async def convert(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(400, "Unsupported file format.")
    raw = await file.read()
    if len(raw) > MAX_MB * 1024 * 1024:
        raise HTTPException(413, f"File is larger than {MAX_MB} MB.")

    temp = UPLOADS / f"{uuid.uuid4().hex}{ext}"
    temp.write_bytes(raw)
    try:
        png = convert_to_png_bytes(str(temp))
        result = extract_dfd(str(temp))
        errors = validate_dfd(result)
        if errors:
            raise HTTPException(422, {"message": "AI returned JSON that failed validation.", "errors": errors, "dfd_json": result})
        return {"success": True, "filename": file.filename, "dfd_json": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        try: temp.unlink(missing_ok=True)
        except Exception: pass

@app.post("/api/validate")
async def validate(payload: dict):
    errors = validate_dfd(payload)
    return {"valid": len(errors) == 0, "errors": errors}

@app.post("/api/download")
async def download(payload: dict):
    path = UPLOADS / f"dfd_{uuid.uuid4().hex}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return FileResponse(path, media_type="application/json", filename="dfd.json")


@app.post("/api/audit")
async def audit_dfd_endpoint(payload: dict):
    """Check a generated DFD JSON object against structural DFD rules."""
    dfd_json = payload.get("dfd_json", payload)

    if not isinstance(dfd_json, dict):
        raise HTTPException(
            status_code=422,
            detail="A valid DFD JSON object is required."
        )

    try:
        return audit_dfd(dfd_json)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"DFD audit failed: {exc}"
        ) from exc

FRONTEND = BASE / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")