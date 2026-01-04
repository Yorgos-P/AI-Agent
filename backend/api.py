from fastapi import BackgroundTasks, FastAPI, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path
from langchain_core.messages import HumanMessage, ToolMessage
from graph import ai_agent
from ingest import pc, ingest
import shutil
from pydantic import BaseModel
import json
import boto3 
import tempfile
import os

s3 = boto3.client("s3")
app = FastAPI()

origins = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:8501,http://127.0.0.1:8501",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatIn(BaseModel):
    chat: str | None 
    session_id: str | None
    saved_name: str | None = None


class ChatOut(BaseModel):
    response: str
    download_link: str | None = None

@app.post("/upload")
async def add_file(file: UploadFile, session_id: str = Form(...)):

    saved_name = f"{session_id}_{file.filename}"
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / file.filename 
            file.file.seek(0)
            with tmp_path.open("wb") as new:
                shutil.copyfileobj(file.file, new)
            ingest(str(tmp_path), session_id)
            s3.upload_file(str(tmp_path), "towardschange", "data/" + saved_name)
    finally:
        await file.close()
    return {"saved_name": saved_name}



@app.post("/chat", response_model=ChatOut)
def chat(payload: ChatIn) -> ChatOut:
    if not payload.saved_name:
        raise HTTPException(status_code=400, detail="Please upload the file first.")
    if not payload.saved_name.startswith(f"{payload.session_id}_"):
        raise HTTPException(status_code=403, detail="Invalid session_id or filename.")

    try:
        response = ai_agent.invoke({"messages": [HumanMessage(content = payload.chat)], 
                                    "bucket_key": "data/" + payload.saved_name,
                                    "session_id": payload.session_id})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chat agent failed: {exc}") from exc
    
    final_response = response["messages"][-1].content

    edited = False
    tool_msg = None

    for m in response["messages"]:
        if isinstance(m, ToolMessage) and m.name == "document_editing_wrapper":
            tool_msg = m
            break
    if tool_msg:
        json_msg = json.loads(tool_msg.content)
        edited = bool(json_msg.get("edited"))
    
    if edited:
        return ChatOut(response = final_response, download_link = "/download")
    return ChatOut(response = final_response)


@app.get("/download/{saved_name}")
def download(saved_name: str, background_tasks: BackgroundTasks):
    try:
        safe_name = Path(saved_name).name
        key = f"data_out/{safe_name}"

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=Path(safe_name).suffix)
        tmp_path = Path(tmp.name)
        tmp.close()

        try:
            s3.download_file("towardschange", key, str(tmp_path))
        except Exception as exc:
            tmp_path.unlink(missing_ok=True)
            raise HTTPException(status_code=404, detail=f"Edited file not found: {exc}") from exc

        background_tasks.add_task(tmp_path.unlink, missing_ok=True)

        media_type = "application/pdf" if tmp_path.suffix.lower() == ".pdf" else \
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        download_name = "edited_document.pdf" if tmp_path.suffix.lower() == ".pdf" else "edited_document.docx"
        return FileResponse(str(tmp_path), media_type=media_type, filename=download_name)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unable to stream file: {exc}") from exc


@app.post("/reset/{session_id}")
def reset_session(session_id: str):
    try:
        index = pc.Index(host = "https://langchain-langgraph-58vo94i.svc.aped-4627-b74a.pinecone.io")
        index.delete_namespace(namespace = session_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete Pinecone namespace: {exc}") from exc

    return {"status": "reset", "detail": "Session files cleared and namespace deleted"}
