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
    def filter_by_category(filenames: List[str], files_dict: dict, category: str) -> List[str]:
        """Filter filenames by category."""
        return [
            f for f in filenames
            if files_dict.get(f, {}).get('category') == category
        ]
