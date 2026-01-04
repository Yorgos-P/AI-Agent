import requests
import streamlit as st
import uuid

API_URL = "https://my-api-433345942906.europe-west1.run.app"

st.set_page_config(page_title="🔱 Trident Bot")
st.title("🔱 Trident Bot")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "download_ready" not in st.session_state:
    st.session_state.download_ready = False
if "download_payload" not in st.session_state:
    st.session_state.download_payload = None
if "download_filename" not in st.session_state:
    st.session_state.download_filename = "edited_document"
if "download_mime" not in st.session_state:
    st.session_state.download_mime = "application/octet-stream"
if "saved_name" not in st.session_state:
    st.session_state.saved_name = None


print(f"[streamlit rerun] download_ready={st.session_state.download_ready}")


def upload_document():
    uploaded = st.file_uploader("Upload a document", type=["pdf", "docx"],
                                key = f"{st.session_state.session_id}" )
    if uploaded and st.button("Click Here to Upload"):
        files = {"file": (uploaded.name, uploaded.getvalue(), uploaded.type)}
        try:
            with st.spinner("Uploading document, please wait"):
                r = requests.post(f"{API_URL}/upload", files=files, 
                                  data = {"session_id": st.session_state.session_id}, timeout=300)
            r.raise_for_status()
            data = r.json()
            st.session_state.saved_name = data["saved_name"]
            st.success("Document uploaded and ingested.")
        except requests.RequestException as exc:
            st.error(f"Upload failed: {exc}")


def render_chat(session_id: str, saved_name: str):
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_text = st.chat_input("Ask something…")
    if not user_text:
        return

    st.session_state.messages.append({"role": "user", "content": user_text})
    with st.chat_message("user"):
        st.markdown(user_text)

    try:
        with st.spinner("Processing response"):
            r = requests.post(f"{API_URL}/chat", 
                          json={"chat": 
                          user_text, "session_id": session_id, "saved_name": saved_name}, 
                          timeout=300)
        data = r.json()
        if r.status_code != 200:
            reply = data.get("detail", r.text)
        else:
            reply = data.get("response", " ")

        st.session_state.download_ready = bool(data.get("download_link"))
        if st.session_state.download_ready:
            try:
                download_resp = requests.get(f"{API_URL}/download/{saved_name}", timeout=60)
                download_resp.raise_for_status()
                disposition = download_resp.headers.get("content-disposition", "attachment; filename=edited_document")
                filename = disposition.split("filename=")[-1].strip('"; ')
                st.session_state.download_payload = download_resp.content
                st.session_state.download_filename = filename
                st.session_state.download_mime = download_resp.headers.get("content-type", "application/octet-stream")
            except requests.RequestException as exc:
                st.error(f"Download preparation failed: {exc}")
                st.session_state.download_ready = False
                st.session_state.download_payload = None
    except requests.RequestException as exc:
        st.error(f"Error calling API: {exc}")
        if "r" in locals() and r is not None:
            st.write("Status:", r.status_code)
            st.write("Body:", r.text)
        reply = f"Error calling API: {exc}"
        st.session_state.download_ready = False
        st.session_state.download_payload = None

    st.session_state.messages.append({"role": "assistant", "content": reply})
    with st.chat_message("assistant"):
        st.markdown(reply)


def render_download():
    if not st.session_state.download_ready:
        return

    payload = st.session_state.download_payload
    filename = st.session_state.download_filename
    mime = st.session_state.download_mime

    if not payload:
        st.error("No file available to download.")
        st.session_state.download_ready = False
        return

    st.download_button(
        label=f"Download {filename}",
        data=payload,
        file_name=filename,
        mime=mime,
    )


def render_reset(session_id: str):
    if st.button("Refresh Conversation & Upload New File"):
        # If the user never uploaded a file, there is nothing on the backend to clear.
        if not st.session_state.get("saved_name"):
            st.success("Session cleared.")
        else:
            try:
                with st.spinner("Clearing session"):
                    r = requests.post(f"{API_URL}/reset/{session_id}", timeout=300)
                r.raise_for_status()
                st.success("Session cleared.")
            except requests.RequestException as exc:
                st.error(f"Reset failed: {exc}")
        st.session_state.messages.clear()
        st.session_state.download_ready = False
        st.session_state.download_payload = None
        st.session_state.download_filename = "edited_document"
        st.session_state.download_mime = "application/octet-stream"
        st.session_state.saved_name = None
        st.session_state.session_id = str(uuid.uuid4())
        st.rerun()


upload_document()
render_chat(st.session_state["session_id"], st.session_state["saved_name"])
render_download()
render_reset(st.session_state["session_id"])
