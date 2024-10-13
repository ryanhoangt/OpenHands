import litellm


def get_token_count_from_text(model_name: str, text: str):
    """
    Get the token count from the given text using the specified model.
    Args:
        model_name (str): The name of the model to use for token counting.
        text (str): The input text.
    """
    return litellm.token_counter(model=model_name, text=text)
