"""
This module contains utility functions for handling Markdown content.
Functions include loading language mappings, generating translation prompts,
and processing specific Markdown structures such as comments and URLs.
"""

import re
import tiktoken
from pathlib import Path
from urllib.parse import urlparse
import logging
from src.utils.file_utils import get_unique_id
from src.config.constants import SUPPORTED_IMAGE_EXTENSIONS
from src.utils.file_utils import generate_translated_filename

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def generate_prompt_template(output_lang: str, document_chunk: str, is_rtl: bool) -> str:
    """
    Generate a translation prompt for a document chunk, considering language direction.

    Args:
        output_lang (str): The target language for translation.
        document_chunk (str): The chunk of the document to be translated.
        is_rtl (bool): Whether the target language is right-to-left.

    Returns:
        str: The generated translation prompt.
    """
    # Check if there is only one line in the document
    if len(document_chunk.split("\n")) == 1:
        # Generate prompt for single line translation
        prompt = f"Translate the following text to {output_lang}. NEVER ADD ANY EXTRA CONTENT OUTSIDE THE TRANSLATION. TRANSLATE ONLY WHAT IS GIVEN TO YOU.. MAINTAIN MARKDOWN FORMAT\n\n{document_chunk}"
    else:
        prompt = f"""
        Translate the following markdown file to {output_lang}.
        Make sure the translation does not sound too literal. Make sure you translate comments as well.
        Do not translate any entities, such as variable names, function names, or class names, but keep them in the file.
        Do not translate any urls or paths, but keep them in the file.
        """

    if is_rtl:
        prompt += "Please write the output from right to left, respecting that this is a right-to-left language.\n"
    else:
        prompt += "Please write the output from left to right.\n"

    # Append the actual document chunk to be translated
    prompt += "\n" + document_chunk

    return prompt

def get_tokenizer(encoding_name: str):
    """
    Get the tokenizer based on the encoding name.

    Args:
        encoding_name (str): The name of the encoding.

    Returns:
        tiktoken.Encoding: The tokenizer for the given encoding.
    """
    return tiktoken.get_encoding(encoding_name)

def count_tokens(text: str, tokenizer) -> int:
    """
    Count the number of tokens in a given text using the tokenizer.

    Args:
        text (str): The text to tokenize.
        tokenizer (tiktoken.Encoding): The tokenizer to use.

    Returns:
        int: The number of tokens in the text.
    """
    return len(tokenizer.encode(text))

def split_markdown_content(content: str, max_tokens: int, tokenizer) -> list:
    """
    Split the markdown content into smaller chunks based on code blocks, blockquotes, or HTML.

    Args:
        content (str): The markdown content to split.
        max_tokens (int): The maximum number of tokens allowed per chunk.
        tokenizer: The tokenizer to use for counting tokens.

    Returns:
        list: A list of markdown chunks.
    """
    chunks = []
    block_pattern = re.compile(r'(```[\s\S]*?```|<.*?>|(?:>\s+.*(?:\n>.*|\n(?!\n))*\n?)+)')
    parts = block_pattern.split(content)
    
    current_chunk = []
    current_length = 0

    for part in parts:
        part_tokens = count_tokens(part, tokenizer)
        
        if current_length + part_tokens <= max_tokens:
            current_chunk.append(part)
            current_length += part_tokens
        else:
            if block_pattern.match(part):
                if current_chunk:
                    chunks.append(''.join(current_chunk))
                chunks.append(part)
                current_chunk = []
                current_length = 0
            else:
                words = part.split()
                for word in words:
                    word_tokens = count_tokens(word + ' ', tokenizer)
                    if current_length + word_tokens > max_tokens:
                        chunks.append(''.join(current_chunk))
                        current_chunk = [word + ' ']
                        current_length = word_tokens
                    else:
                        current_chunk.append(word + ' ')
                        current_length += word_tokens

    if current_chunk:
        chunks.append(''.join(current_chunk))

    return chunks

def process_markdown(content: str, max_tokens=4096, encoding='o200k_base') -> list: # o200k_base is for GPT-4o, cl100k_base is for GPT-4 and GPT-3.5
    """
    Process the markdown content to split it into smaller chunks.

    Args:
        content (str): The markdown content to process.
        max_tokens (int): The maximum number of tokens allowed per chunk.
        encoding (str): The encoding to use for the tokenizer.

    Returns:
        list: A list of processed markdown chunks.
    """
    tokenizer = get_tokenizer(encoding)
    return split_markdown_content(content, max_tokens, tokenizer)

def update_image_link(md_file_path: Path, markdown_string: str, language_code: str, docs_dir: Path) -> str:
    """
    Update image links in the markdown content to reflect the translated images.

    Args:
        md_file_path (Path): The path to the markdown file.
        markdown_string (str): The markdown content as a string.
        language_code (str): The language code for the translation.
        docs_dir (Path): The directory where the documentation is stored.

    Returns:
        str: The updated markdown content with new image links.
    """
    logger.info("UPDATING IMAGE LINKS")
    pattern = r'!\[(.*?)\]\((.*?)\)' # Capture both alt text and link
    matches = re.findall(pattern, markdown_string)

    for alt_text, link in matches:
        parsed_url = urlparse(link)
        if parsed_url.scheme in ('http', 'https'):
            continue # Skip web URLs

        path = Path(parsed_url.path)  # Convert to Path object
        file_ext = path.suffix  # Get the file extension

        if file_ext.lower() in SUPPORTED_IMAGE_EXTENSIONS:
            if md_file_path.startswith(str(docs_dir)):
                rel_levels = md_file_path.relative_to(docs_dir).parts
                translated_folder = ('../' * len(rel_levels)) + 'translated_images'
            else: # is a readme image
                translated_folder = "./translated_images"

            actual_image_path = md_file_path.parent / link
            new_filename = generate_translated_filename(str(actual_image_path), language_code)
            updated_link = f"{translated_folder}/{new_filename}"

            markdown_string = markdown_string.replace(link, updated_link)

    return markdown_string
