from docx import Document
from ingest import llm 
import ast



def task_splitter(query: str):
    """
    This function is always used but only useful when a singular user query contains multiple
    edit requests. The function's job is to split the a multi-edit query into individual 'edit intents'.
    Look at the example below
    
    Args:
        query: The full original user query
    Returns:
        A list where each element corresponds to a single 'edit intent'
    Example:
        query = “Based on the uploaded document, replace the client name with ACME Corp, 
        update the date to January 15, 2025, and change all monetary amounts to euros.”
        
        answer = ["Replace the client name with Acme Corp", "Update the date to January 15, 2025",
                    "Change all monetary amounts to euros"]
    """
    prompt = f""" You are an intent decomposition engine.
    Your task:
    Given a single user request, identify all distinct, executable actions requested.
    Each action must correspond to exactly one intent.

    RULES:
    -Do not infer new actions.
    -Do not merge different actions into one.
    -Do not split object lists unless a new action is explicitly implied.

    - You must return the actions as a raw Python list. No markdown, no fences, no commentary.
    - Each action should be a short imperative phrase.
    - Do not include explanations.
    
    User request:
    {query} """

    answer = llm.invoke(prompt).content
    return answer


def find_list(query: str):
    """
    Transforms a singular sentence that pertains to editing into a short sentence
    'find sentence'. Look at example below

    Args:
        query: The entire user query or a piece of the query depending on whether
        the user asked for multiple edits in one query.
    Returns:
        A short 'Find <things-to-locate>' sentence
    Example:
        query = Change the monetary values to dollars
        answer = Find monetary values
    """

    prompt = f"""You are a query rewriter.

        Input: a list of actions or single action instruction about editing a document.
        Task: Output sentences in the form:

        "Find <things-to-locate>."

        Rules:
        - Based on the input, for each action, you must determine what you must find in the text
        - Only output the "Find ..." sentence. No extra text.
        - Do not add new details.
        - The output should STRICTLY be a Python list where each entry corresponds to a single "Find <thing-to-locate>." string. 
        - Do not wrap the response in markdown or code fences

        Action:
        {query}
        """
    answer = llm.invoke(prompt).content
    return answer


def target_finder(query: str, vector_store, top_k, session_id):
    """
    Using the 'find <thing-to-locate>' from the above function, the target_finder()
    function returns a list of elements pertaining to the relevant keywords by searching
    the vector database. Look at the example below.
    
    Args:
        query: The "find <thing-to-locate>" string.
        vector_store: The specific namespace of the Pinecone vector store 
        top_k: The number of top chunks to keep
        session_id: The unique user session id generated for every Streamlit session
    Returns:
        A list of relevant keywords from the uploaded document 
    Example:
        query = Find monetary values
        answer = ['€20', '€333']

    """

    query = ast.literal_eval(query)[0]
    retrieved_chunks = vector_store.similarity_search(query, k = top_k, namespace = session_id)
    context_text = "\n\n".join(
        f"Source: {doc.metadata}\nContent: {doc.page_content}"
        for doc in retrieved_chunks
        )       
    print("This is before processing the LLM processes the prompt")

    prompt = f"""You are an information extraction engine.
        Goal:        
            Extract only concrete, searchable keywords based on the Question provided below.
            Do NOT add related entities, synonyms, categories, or examples.

        Rules:
        - If the Question asks to find something very specific, ONLY output that keyword if it exists in the context.
        - If the Question is slightly more conceptual, (e.g find all dates), then find all keywords pertaining to that concept.
        - Output the exact text span from Context, preserving punctuation/commas exactly.
        - If there is no explicit target in the Question, output [].
        - Output RAW Python list only. No markdown, no commentary, no fences.
        - The list can have only one element, it need not have multiple elements

        Context (for disambiguation only; never add items from it):
        {context_text}

        Question:
        {query}

            """
    answer = llm.invoke(prompt).content
    print("This is after it processes the prompt")

    return answer


def replace(original_query: str, keywords: str):
    """
    Given a list of relevant keywords from the above function, this function 
    transforms each query into what the user initially requested. Look at the 
    example below

    Args:
        original_query: The user's original query (or part of the query if multiple edits were requested)
        keywords: A list of relevant keywords from the uploaded documents that will be edited
    
    Returns:
        A list of transformed keywords
    Example:
        original_query = Change all monetary values to dollars
        keywords = ['€20', '€333']
        answer = ['$20', '$333']
    """

    prompt = f""" You are a precise list transformer.
    GOAL:
    -Your job is to apply replacement instructions to every item in a list.
    INPUT:
    -You are given a query (the replacement instructions) and a list where you must apply the instruction to each element
    RULES:
    -You must not invent extra replacements. You must preserve the list length and item order.
    -You output ONLY the transformed list in the requested format.
    -You must output a RAW Python list. No markdown, no commentary, no fences
    Query: {original_query}
    List: {keywords}

"""
    answer = llm.invoke(prompt).content
    return answer

def replace_keyword(doc: Document, target: str, replacement: str) -> int:
    """
    Given the the target and replacemenet lists from all the above work, 
    this function applies replacements for individual pairs
    and is only called inside the apply_replacement_in_doc function

    Args:
        target: A singular keyword that exists in the text (many instances could exist)
        replacement: The keyword to replace the above 'target' keyword
    """

    def replace_in_paragraph(p) -> None:
        if target not in p.text: 
            return
        new_text = p.text.replace(target, replacement)

        if p.runs:
            p.runs[0].text = new_text
            for r in p.runs[1:]:
                r.text = ""
        else:
            p.add_run(new_text)

    def walk(container) -> None:
        for p in container.paragraphs:
            replace_in_paragraph(p)
        for table in container.tables:
            for row in table.rows:
                for cell in row.cells:
                    walk(cell)

    walk(doc)  

    for section in doc.sections:  
        walk(section.header)
        walk(section.footer)

    return doc

def apply_replacements_in_doc(doc: Document, target_list_string: str, replacement_list_string: str):
    """
    The last function in the editing logic. Given the list of target keywords and 
    replacement keywords (what we must replace the target by), this function applies the 
    replacements in the doc.

    Args:
        doc = The uploaded document
        target_list_string = A list of all keywords in the doc that must be replaced
        replacement_list_string = The corresponding replacements for each target keyword from the above list
    Returns:
        The modified document
    """

    for target, replacement in zip(target_list_string, replacement_list_string):
        if not isinstance(target, str):
            target = str(target)
        if not isinstance(replacement, str):
            replacement = str(replacement)
        doc = replace_keyword(doc, target, replacement)
    
    return doc

    




