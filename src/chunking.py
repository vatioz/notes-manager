"""
Adaptive line-based chunking for note files.
Merges short lines, splits long lines, and prepends filename context to each chunk.
"""
from dataclasses import dataclass
from typing import List
import re


@dataclass
class Chunk:
    """Represents a text chunk with metadata."""
    text: str
    filename: str
    line_start: int
    line_end: int


def chunk_file(filename: str, content: str, min_chars: int = 100, max_chars: int = 500) -> List[Chunk]:
    """
    Chunk a file's content using adaptive line-based strategy.
    
    Strategy:
    1. Split by lines
    2. Skip blank lines
    3. Merge consecutive short lines until reaching min_chars
    4. Split any chunk exceeding max_chars at sentence/word boundaries
    5. Prepend filename to each chunk for context
    
    Args:
        filename: Name of the file being chunked
        content: File content to chunk
        min_chars: Minimum characters per chunk (merges lines below this)
        max_chars: Maximum characters per chunk (splits lines above this)
    
    Returns:
        List of Chunk objects with text, filename, and line range
    """
    if not content or not content.strip():
        return []
    
    lines = content.split('\n')
    chunks = []
    
    current_chunk_lines = []
    current_chunk_text = []
    current_start_line = None
    
    for line_idx, line in enumerate(lines, start=1):
        # Skip completely blank lines but track line numbers
        if not line.strip():
            continue
        
        # Initialize chunk start if needed
        if current_start_line is None:
            current_start_line = line_idx
        
        current_chunk_lines.append(line_idx)
        current_chunk_text.append(line)
        joined_text = '\n'.join(current_chunk_text)
        
        # Check if we've reached minimum length
        if len(joined_text) >= min_chars:
            # Create chunk(s) from accumulated text
            chunks_from_text = _split_if_needed(
                joined_text,
                filename,
                current_start_line,
                current_chunk_lines[-1],
                max_chars
            )
            chunks.extend(chunks_from_text)
            
            # Reset accumulators
            current_chunk_lines = []
            current_chunk_text = []
            current_start_line = None
    
    # Handle any remaining text that didn't reach min_chars
    if current_chunk_text:
        joined_text = '\n'.join(current_chunk_text)
        chunks_from_text = _split_if_needed(
            joined_text,
            filename,
            current_start_line,
            current_chunk_lines[-1],
            max_chars
        )
        chunks.extend(chunks_from_text)
    
    return chunks


def _split_if_needed(text: str, filename: str, line_start: int, line_end: int, max_chars: int) -> List[Chunk]:
    """
    Split text into chunks if it exceeds max_chars, otherwise return single chunk.
    Prepends filename context to each chunk.
    """
    # Prepend filename for context
    contextualized_text = f"[{filename}] {text}"
    
    if len(contextualized_text) <= max_chars:
        return [Chunk(
            text=contextualized_text,
            filename=filename,
            line_start=line_start,
            line_end=line_end
        )]
    
    # Need to split - try sentence boundaries first
    chunks = []
    
    # Split on sentence boundaries: '. ', '? ', '! '
    sentence_pattern = r'([.?!])\s+'
    parts = re.split(sentence_pattern, text)
    
    # Reconstruct sentences (re.split separates the punctuation)
    sentences = []
    i = 0
    while i < len(parts):
        if i + 1 < len(parts) and parts[i + 1] in '.?!':
            sentences.append(parts[i] + parts[i + 1])
            i += 2
        else:
            sentences.append(parts[i])
            i += 1
    
    # If no sentence splits found, fall back to word boundaries
    if len(sentences) == 1:
        sentences = _split_by_words(text, max_chars - len(f"[{filename}] "))
    
    # Group sentences into chunks respecting max_chars
    current_chunk = []
    for sentence in sentences:
        test_text = ' '.join(current_chunk + [sentence])
        contextualized = f"[{filename}] {test_text}"
        
        if len(contextualized) <= max_chars:
            current_chunk.append(sentence)
        else:
            # Flush current chunk if not empty
            if current_chunk:
                chunk_text = f"[{filename}] {' '.join(current_chunk)}"
                chunks.append(Chunk(
                    text=chunk_text,
                    filename=filename,
                    line_start=line_start,
                    line_end=line_end
                ))
                current_chunk = []
            
            # If single sentence is too long, split it by words
            if len(f"[{filename}] {sentence}") > max_chars:
                word_chunks = _split_by_words(sentence, max_chars - len(f"[{filename}] "))
                for word_chunk in word_chunks:
                    chunks.append(Chunk(
                        text=f"[{filename}] {word_chunk}",
                        filename=filename,
                        line_start=line_start,
                        line_end=line_end
                    ))
            else:
                current_chunk.append(sentence)
    
    # Flush any remaining
    if current_chunk:
        chunk_text = f"[{filename}] {' '.join(current_chunk)}"
        chunks.append(Chunk(
            text=chunk_text,
            filename=filename,
            line_start=line_start,
            line_end=line_end
        ))
    
    return chunks if chunks else [Chunk(
        text=contextualized_text[:max_chars],
        filename=filename,
        line_start=line_start,
        line_end=line_end
    )]


def _split_by_words(text: str, max_len: int) -> List[str]:
    """Split text by word boundaries to respect max length."""
    words = text.split()
    chunks = []
    current = []
    
    for word in words:
        test = ' '.join(current + [word])
        if len(test) <= max_len:
            current.append(word)
        else:
            if current:
                chunks.append(' '.join(current))
                current = [word]
            else:
                # Single word exceeds limit - force split
                chunks.append(word[:max_len])
                if len(word) > max_len:
                    # Remaining part - could recursively handle but truncate for simplicity
                    current = [word[max_len:]]
    
    if current:
        chunks.append(' '.join(current))
    
    return chunks if chunks else [text[:max_len]]
