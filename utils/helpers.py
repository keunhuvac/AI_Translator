# /utils/helpers.py  (Formerly utils.py)
import re
import logging

logger = logging.getLogger(__name__)

def contains_chinese(text):
    """Checks if the text contains Chinese characters."""
    if not text: # Handle None or empty string
        return False
    # Includes common CJK Unified Ideographs ranges
    return bool(re.search(r'[\u4e00-\u9fff\u3400-\u4dbf\uF900-\uFAFF]', text))

def split_text(text, max_chunk_size=8000):
    """Splits text into smaller chunks by newline, handling oversized paragraphs."""
    if not text:
        return []
    paragraphs = text.split('\n')
    chunks = []
    current_chunk = ""
    for p in paragraphs:
        p_stripped = p.strip() # Handle paragraphs with only whitespace
        if not p_stripped: # Skip empty lines/paragraphs
            if current_chunk.strip(): # Add newline to preserve paragraph breaks if needed
                current_chunk += "\n"
            continue

        # If adding the current paragraph doesn't exceed the limit
        if len(current_chunk) + len(p) + 1 < max_chunk_size:
            # Add to the current chunk, prefixing with newline if chunk not empty
            current_chunk += ("\n" if current_chunk else "") + p
        else:
            # Add the completed chunk (if it has content)
            if current_chunk.strip():
                chunks.append(current_chunk)

            # Handle the current paragraph (p)
            # If this paragraph itself is longer than the limit
            if len(p) > max_chunk_size:
                logger.warning(f"Segment longer than max_chunk_size ({len(p)} > {max_chunk_size}). Splitting mid-segment.")
                # Split the oversized paragraph
                for i in range(0, len(p), max_chunk_size):
                    sub_chunk = p[i:i+max_chunk_size]
                    if sub_chunk.strip(): # Only add non-empty sub-chunks
                        chunks.append(sub_chunk)
                current_chunk = "" # Reset current chunk after splitting oversized one
            else:
                # Start a new chunk with the current paragraph
                current_chunk = p

    # Add the last remaining chunk if it has content
    if current_chunk.strip():
        chunks.append(current_chunk)

    return chunks
