"""Search functionality for files and content."""

from typing import Callable, List


class SearchEngine:
    """Handles searching of files and content."""
    
    @staticmethod
    def search_filenames(filenames: List[str], query: str) -> List[str]:
        """
        Search filenames (case-insensitive).
        Returns list of matching filenames.
        """
        if not query:
            return filenames
        
        query_lower = query.lower()
        matches = []
        
        for filename in filenames:
            if query_lower in filename.lower():
                matches.append(filename)
        
        return matches
    
    @staticmethod
    def search_file_content(content: str, query: str, max_snippets: int = 3) -> List[str]:
        """
        Search within file content for query.
        Returns list of snippet contexts where query was found.
        """
        if not query:
            return []
        
        snippets = []
        lines = content.split('\n')
        query_lower = query.lower()
        
        for i, line in enumerate(lines):
            if query_lower in line.lower():
                # Create snippet with context
                start = max(0, i - 1)
                end = min(len(lines), i + 2)
                snippet_lines = lines[start:end]
                
                # Highlight the matching line
                snippet = '\n'.join(snippet_lines)
                snippets.append((i + 1, snippet))  # Line number, snippet
                
                if len(snippets) >= max_snippets:
                    break
        
        return snippets

    @staticmethod
    def search_filenames_or_content(
        filenames: List[str],
        query: str,
        content_loader: Callable[[str], str],
    ) -> List[str]:
        """
        Search filenames and file contents (case-insensitive).
        Returns list of matching filenames.
        """
        if not query:
            return filenames

        query_lower = query.lower()
        matches = []

        for filename in filenames:
            if query_lower in filename.lower():
                matches.append(filename)
                continue

            try:
                content = content_loader(filename)
            except Exception:
                content = ''

            if query_lower in content.lower():
                matches.append(filename)

        return matches
    
    @staticmethod
    def search_semantic(
        filenames: List[str],
        query: str,
        vector_store,
        embedding_client
    ) -> List[str]:
        """
        Search using semantic similarity via vector embeddings.
        
        Args:
            filenames: List of filenames to search within (scoping)
            query: Search query text
            vector_store: VectorStore instance
            embedding_client: EmbeddingClient instance
        
        Returns:
            List of matching filenames, ranked by semantic similarity
        """
        if not query or not filenames:
            return filenames if not query else []
        
        try:
            # Generate embedding for the query
            query_embedding = embedding_client.embed_query(query)
            
            # Search vector store with filename filter
            results = vector_store.search(
                query_embedding=query_embedding,
                n_results=50,  # Get more results to ensure good coverage
                filter_filenames=filenames
            )
            
            # Deduplicate by filename while preserving order (best match first)
            seen = set()
            ranked_filenames = []
            for result in results:
                if result.filename not in seen:
                    seen.add(result.filename)
                    ranked_filenames.append(result.filename)
            
            return ranked_filenames
        
        except Exception as e:
            print(f"Semantic search error: {e}")
            # Fallback to returning all files if search fails
            return filenames
    
    @staticmethod
    def filter_by_category(filenames: List[str], files_dict: dict, category: str) -> List[str]:
        """Filter filenames by category."""
        return [
            f for f in filenames
            if files_dict.get(f, {}).get('category') == category
        ]
