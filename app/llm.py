import os
from openai import OpenAI


def build_messages(user_message: str)-> list[dict[str,str]]:
    """
    Build a message for the OpenAI API.

    Args:
        user_message (str): The user's message.

    Returns:
        list[dict[str,str]]: A list of message dictionaries for the OpenAI API.
    """
    return [
        {"role": "user", "content": user_message}
    ]
def ask_llm(
    messages: list[dict[str, str]],
    ) -> str:
    """
    Ask the language model a question.

    Args:
        user_message (str): The user's message.

    Returns:
        str: The response from the language model.
    """
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    model = os.getenv("LLM_MODEL")
    if not api_key:
        raise RuntimeError(
            "LLM_API_KEY environment variable is not set."
            )
    if not model:
        raise RuntimeError(
            "LLM_MODEL environment variable is not set."
            )
    client = OpenAI(
        api_key=api_key, 
        base_url=base_url or None
        )
    
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.7,
        # max_tokens=150
    )
    content = response.choices[0].message.content
    return content or "No response from the language model."