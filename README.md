# AI-Agent
## PROJECT OVERVIEW
- An AI bot hosted on Google Cloud Run that can edit, summarize and answer questions based on the user's uploaded files
- Accepted formats: Word, PDF

## SERVICES USED
- Google Cloud Run Services to host the website
- Pinecone to store the chunked text of the uploaded file
- AWS S3 Bucket to store files for downstream use (e.g when edits are requested)
- OpenAI's GPT

## DATA FLOW
### UPLOAD
Streamlit --> FastAPI endpoint --> Ingested & Processed (Chunking) by the backend Google Cloud container instance --> Sent to Pinecone & AWS S3.

### CHAT
Streamlit --> FastAPI endpoint --> Pinecone/S3 (depending on the job) --> Backend Agent Creates Response --> FastAPI --> Streamlit

## APPLICATION LOGIC

### QA
Simple RAG application. Based on the document (PDF or docx), an appropriate loader is chosen. The text is chunked and stored in Pinecone.
I use OpenAI's "text-embedding-3-small" model for the embeddings

### Summarization 
The whole document is downloaded and processed by a function that calls OpenAI's gpt-4o model and outputs a summary using prompt engineering

### Editing
1. Since one query can contain multiple 'edit intents' (a user requesting more than one modification), the agent first breaks up the query to individual 'edit intents'
2. The agent then retrieves relevant chunks from Pinecone for the specific edit intent (this is because the requested edits can be conceptual)
3. Based on the chunks received the agent needs to narrow down specific keywords relevant to the edit intent
4. The agent then transforms those keywords based on what the user requested
5. Finally the agent replaces those keywords in the document
6. (If the file is a PDF, it is converted to Word where the edits are applied and then converted back to PDF)

## STORING API KEYS
All API keys are stored in Google Cloud's Secret Manager.




   
