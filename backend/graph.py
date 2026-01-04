from rag import retriever, generator
from document_editing import find_list, target_finder, replace, apply_replacements_in_doc, task_splitter
import ast
import json
from typing import Annotated, Sequence, TypedDict
from pathlib import Path
import subprocess
from pdf2docx import Converter
from docx import Document
from langchain_core.messages import BaseMessage, ToolMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph.message import add_messages
from langgraph.graph import StateGraph, END
import magic
from langchain_pinecone import PineconeVectorStore
from ingest import embedding, llm
from pypdf import PdfReader
import tempfile
import boto3


s3 = boto3.client("s3")

def is_PDF(path: str):
    """
    Checks if file is a PDF or Docx using the magic library by reading the
    file's bytes instead of just checking the extension

    Args:
        path: The local file path to check

    Returns:
        'PDF' if the file is a pdf file
        'Word' if the file is a docx file
        Raises a a ValueError otherwise
    
    """
    mime = magic.from_file(path, mime=True)
    if mime == "application/pdf":
        return "PDF"
    elif mime in {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    }:
        return "Word"
    else:
        raise ValueError(f"Unsupported MIME type: {mime}")
    



class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    bucket_key: str
    session_id: str




@tool
def rag_wrapper(query: str, session_id: str):
    """"Outputs response to a question asked regarding the document"""

    vector_store = PineconeVectorStore(index_name = 'langchain-langgraph',
                                       embedding = embedding)
    
    retrieved_chunks = retriever(query, vector_store, 10, session_id)
    print(session_id)
    print(retrieved_chunks)
    response = generator(retrieved_chunks, query)
    return response


@tool
def document_editing_wrapper(query: str, bucket_key: str, session_id: str):
    """Apply ALL edits in full_request to the document in ONE call."""
    print(query)

    vector_store = PineconeVectorStore(index_name = 'langchain-langgraph',
                                       embedding = embedding, namespace = session_id)
    
    cannot_find = []
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / Path(bucket_key).name
        s3.download_file("towardschange", bucket_key, str(file_path))
        working_docx = file_path.with_suffix(".working.docx")
        source_type = is_PDF(str(file_path))
        out_dir = Path(tmpdir) / "out"
        out_dir.mkdir(parents = True, exist_ok = True)

        if source_type == "PDF":
            cv = Converter(str(file_path))
            cv.convert(str(working_docx), start=0, end=None)
            cv.close()
            doc = Document(str(working_docx))
        else:
            doc = Document(str(file_path))

        tasks = ast.literal_eval(task_splitter(query))
        print(tasks)

        for task in tasks:
            find_list_ = find_list(task)
            print(find_list_)
            target_keywords = target_finder(find_list_, vector_store, 5, session_id)
            if not ast.literal_eval(target_keywords):
                cannot_find.append(f"Could not {find_list_}")
            print(target_keywords)
            replacement_list = replace(task, target_keywords)
            #print(replacement_list)
            doc = apply_replacements_in_doc(doc, ast.literal_eval(target_keywords), ast.literal_eval(replacement_list))

        if len(cannot_find) == len(tasks):
            response = {"message": "Could not find keywords in the \
                     document corresponding to the requested edit(s)",
                     "edited": False}
            return json.dumps(response)
    
        doc.save(str(working_docx)) #Save the edited document 
        if source_type == "PDF":
            subprocess.run([
                "soffice",
                "--headless",
                "--convert-to", "pdf",
                str(working_docx),
                "--outdir", str(out_dir)
            ], check=True)

            saved_pdf_path = out_dir / f"{working_docx.stem}.pdf"
            s3.upload_file(str(saved_pdf_path), "towardschange", "data_out/" + str(Path(bucket_key).name))
        else:
            s3.upload_file(str(working_docx), "towardschange", "data_out/" + str(Path(bucket_key).name))
        
    if (len(cannot_find) < len(tasks)) and (len(cannot_find) > 0):
        response = {
            "message": "Could not" + ", ".join(cannot_find) + \
                ". All other edit(s) were performed",
            "edited": True
        }


        return json.dumps(response)
    
    response = {"message": "All edits were processed", "edited": True}
    return json.dumps(response)

@tool
def summarization(bucket_key: str):
    """Summarises the document"""

    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / Path(bucket_key).name
        s3.download_file("towardschange", bucket_key, str(file_path))
        if is_PDF(file_path) == "PDF":
            reader = PdfReader(str(file_path))
            document_text = "\n\n".join(page.extract_text() or "" for page in reader.pages)     

        else:
            reader = Document(file_path)
            document_text = "\n".join(p.text for p in reader.paragraphs)

        prompt = f""" You are a careful document summarization agent.

        Goal: Summarize the document to help the user understand the main ideas quickly.

        Default behavior (when the user does NOT request a format):
        - Write a natural-language summary in a few short paragraphs.
        - Include the most important conclusions, decisions, risks, and action items.
        - Keep it concise and neutral.
        - If the document is long, prioritize what matters most.

        Formatting rule:
        - Do NOT use rigid headings, bullet schemas, tables, JSON, or a template unless the user explicitly asks for a specific output format.
        - If the user requests a format (e.g., “bullet points,” “JSON,” “one page,” “executive summary,” “include action items”), follow that request exactly.

        Accuracy rules:
        - Use ONLY information from the document.
        - Do not add outside knowledge or guess.
    

        Document:
        {document_text}
    """
        answer = llm.invoke(prompt).content
        return answer

tools = [rag_wrapper, document_editing_wrapper, summarization]
model = llm.bind_tools(tools)
tool_map = {
    "rag_wrapper": rag_wrapper, 
    "document_editing_wrapper": document_editing_wrapper, 
    "summarization": summarization
        }

def agent(state: AgentState) -> AgentState:

    system_prompt = SystemMessage(content = f"""
    You are an assistant that can ONLY perform three tasks using ONLY the provided DOCUMENT:

    ALLOWED TASKS
    1) QUESTION_ANSWERING: Answer questions using the DOCUMENT only by calling the 'rag_wrapper' tool.
    2) EDITING: Editing to the DOCUMENT, only by calling the 'document_editing_wrapper' tool
    3) SUMMARIZING: Summarize the DOCUMENT, only by calling the 'summarization' tool
                                  
    The current bucket_key is {state['bucket_key']} and the session_id is {state['session_id']}
"""
    
)
    
    messages = [system_prompt] + list(state['messages'])
    response = model.invoke(messages)
    final = {"messages": list(state['messages']) + [response]}
    return final


def router(state: AgentState) -> bool:
    """Determine whether to continue or end the
      conversation by checking if the last message has a tool call"""
    
    result = state['messages'][-1]
    return hasattr(result, 'tool_calls') and len(result.tool_calls) > 0

def run_tools(state: AgentState) -> AgentState:
    """Calls appropriate tools"""

    messages = list(state['messages'])
    last_msg = state['messages'][-1]
    query = messages[0].content
    for call in last_msg.tool_calls:
        print(f"Tool: {call['name']} Args: {call['args']}")
        tool = tool_map.get(call['name'])
        if not tool:
            continue
        if call["name"] == "document_editing_wrapper":
            call["args"]["query"] = query
        result = tool.invoke(call['args'])
        messages.append(ToolMessage(
            content = result,
            name = call['name'],
            tool_call_id = call['id']
        ))
    return {"messages": messages}

graph = StateGraph(AgentState)
graph.add_node("central_llm", agent)
graph.add_node("run_tools", run_tools)
graph.add_conditional_edges(
    "central_llm",
    router,
    {
        True: "run_tools",
        False: END
    }
)
graph.add_edge("run_tools", "central_llm")
graph.set_entry_point("central_llm")
ai_agent = graph.compile()


    
    
    
    
