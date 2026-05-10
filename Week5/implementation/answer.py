from pathlib import Path
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.messages import SystemMessage, HumanMessage, convert_to_messages
from langchain_core.documents import Document

from dotenv import load_dotenv


load_dotenv(override=True)

# the same code from day3.ipynb

MODEL = "gpt-4.1-nano"
DB_NAME = str(Path(__file__).parent.parent / "vector_db")

# embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
RETRIEVAL_K = 10  # this is how many chunks gets included in the prompt

SYSTEM_PROMPT = """
You are a knowledgeable, friendly assistant representing the company Insurellm.
You are chatting with a user about Insurellm.
If relevant, use the given context to answer any question.
If you don't know the answer, say so.
Context:
{context}
"""

vectorstore = Chroma(persist_directory=DB_NAME, embedding_function=embeddings)
retriever = vectorstore.as_retriever()
llm = ChatOpenAI(temperature=0, model_name=MODEL)


def fetch_context(question: str) -> list[Document]:
    """
    Retrieve relevant context documents for a question.
    """
    return retriever.invoke(question, k=RETRIEVAL_K)


# this is extra - subtle thing, when we type a message - should we look at the context of the entire chat history, or the context based on the user prompt? for eg. 'Who is avery' followed by 'What did she do before', if we look based on context on the user prompt, we are searching the vector for 'what did she do before', ignoring the information provided about Avery in the chat history.
# a better way, fetch the context not just based on the latest message, but fetch context based on the ENTIRE USER PROMPT aka what user said so far
def combined_question(question: str, history: list[dict] = []) -> str:
    """
    Combine all the user's messages into a single string.
    """
    prior = "\n".join(m["content"] for m in history if m["role"] == "user")
    return prior + "\n" + question


def answer_question(
    question: str, history: list[dict] = []
) -> tuple[str, list[Document]]:
    """
    Answer the given question with RAG; return the answer and the context documents.
    """
    combined = combined_question(question, history)
    docs = fetch_context(
        combined
    )  # fetch context based on the ALL THE USER prompts, we don't just look up the context based on the latest user prompt!
    context = "\n\n".join(doc.page_content for doc in docs)
    system_prompt = SYSTEM_PROMPT.format(context=context)
    messages = [SystemMessage(content=system_prompt)]
    messages.extend(
        convert_to_messages(history)
    )  # make use of history so that llm calls in gradio are not stateless. if we type 'who is avery' and then 'what did she do', the llm can recall that the 'she' is 'avery'
    # convert_to_messages converts OpenAI style messages to LangChain style messages (list of objects)
    messages.append(HumanMessage(content=question))
    response = llm.invoke(messages)
    return response.content, docs
