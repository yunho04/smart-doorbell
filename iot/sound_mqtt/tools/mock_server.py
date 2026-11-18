from fastapi import FastAPI, UploadFile
from pathlib import Path
import time

app = FastAPI()
SAVE_DIR = Path("uploads")
SAVE_DIR.mkdir(exist_ok=True)

@app.post("/upload")
async def upload(file: UploadFile):
    data = await file.read()
    name = f"{int(time.time())}_{Path(file.filename).name}"
    (SAVE_DIR / name).write_bytes(data)
    return {"filename": name, "size": len(data)}
