import litellm

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp'}


def is_image_file(file_name):
    """
    Check if a file is an image file based on its extension.
    Args:
        file_name (str): The name of the file.
    """
    file_name = str(file_name)  # Convert file_name to string
    return any(file_name.endswith(ext) for ext in IMAGE_EXTENSIONS)


def get_token_count_from_text(model_name: str, text: str):
    """
    Get the token count from the given text using the specified model.
    Args:
        model_name (str): The name of the model to use for token counting.
        text (str): The input text.
    """
    return litellm.token_counter(model=model_name, text=text)
