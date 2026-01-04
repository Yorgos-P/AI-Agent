from langchain_community.document_loaders import UnstructuredPDFLoader, UnstructuredWordDocumentLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
import os
from langchain_openai import OpenAIEmbeddings
from langchain_openai import ChatOpenAI
from langchain_pinecone import PineconeVectorStore
import magic 
from pinecone import ServerlessSpec
from pinecone.grpc import PineconeGRPC as Pinecone




llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=os.environ["OPENAI_API_KEY"])
pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
embedding = OpenAIEmbeddings(model='text-embedding-3-small', openai_api_key = os.environ["OPENAI_API_KEY"])





def pick_loader(path: str):
    """
    Checks if file is a PDF or Docx using the magic library by reading the
    file's bytes instead of just checking the extension and returns the appropriate
    loaders.

    Args:
        path: The local file path to check

    Returns:
        UnstructuredPDFLoader() if the file is a PDF
        UnstructuredWordDocumentLoader() if the file is docx
        Raises a a ValueError otherwise
    
    """
    mime = magic.from_file(path, mime=True)
    if mime == "application/pdf":
        loader = UnstructuredPDFLoader(path)
        return loader
    elif mime in {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    }:
        loader = UnstructuredWordDocumentLoader(path)
        return loader
    else:
        raise ValueError(f"Unsupported MIME type: {mime}")

    
def ingest(path: str, session_id: str):
    """
    Ingests the document, splits it into chunks and sends it to the Pinecone
    vector database

    Args:
        path: The path for the document
        session_id: The unique user session id generated for every Streamlit session
    """

    global pc
    index_name = "langchain-langgraph"

    if not pc.has_index(index_name):
        pc.create_index(
            name=index_name,
            vector_type="dense",
            dimension=1536,
            metric="cosine",
            spec=ServerlessSpec(
                cloud="aws",
                region="us-east-1"
            ),
            deletion_protection="disabled"
        )


    splitter = RecursiveCharacterTextSplitter(chunk_size = 2000, chunk_overlap = 200)
    loader = pick_loader(path)
    doc = loader.load()
    chunks = splitter.split_documents(doc)
    vector_store = PineconeVectorStore.from_documents(chunks, index_name = "langchain-langgraph", 
                                                      embedding = embedding, namespace = session_id)
    return vector_store



