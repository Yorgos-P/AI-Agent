from ingest import llm



def retriever(query: str, vector_store, top_k, session_id) -> list:
    """
    Retrieves the relevant chunks from the vector database

    Args:
        query: The user query
        vector_store: The Pinecone vector store
        top_k: The number of top chunks to retrieve
        session_id: The unique user session id generated for every Streamlit session
    """

    relevant_chunks = vector_store.similarity_search(query, k = top_k, namespace = session_id)
    return relevant_chunks



def generator(chunks: list, query: str):
    """
    Generates the response to the question.

    Args:
        chunks: The list of retrieved chunks
        query: The user query 
    """
    context_text = "\n\n".join(
        f"Source: {doc.metadata}\nContent: {doc.page_content}"
        for doc in chunks
        )

    prompt = f"""Use the provided context to provide a concise answer to the user's question. \
    If you cannot find the answer in the provided context, say so. Do not make up information
        Context:
        {context_text}
        Question: {query}
        """
    answer = llm.invoke(prompt).content
    return answer







