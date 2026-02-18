"""Data models and validation for notes management."""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime


@dataclass
class FileMetadata:
    """Metadata for a single file."""
    category: str
    subcategory: Optional[str] = None
    last_viewed: Optional[str] = None
    size_bytes: Optional[int] = None


@dataclass
class CategoryInfo:
    """Information about a category."""
    description: str
    count: int
    files: Optional[List[str]] = None
    subcategories: Optional[Dict[str, List[str]]] = None


class NotesData:
    """Main data structure for notes."""
    
    def __init__(self, data: Dict[str, Any]):
        self.raw_data = data
        self.metadata = data.get('metadata', {})
        self.categories = data.get('categories', {})
        self.files = data.get('files', {})
        self.summary = data.get('summary', {})
    
    def get_all_files_in_category(self, category: str, subcategory: Optional[str] = None) -> List[str]:
        """Get all files in a specific category/subcategory."""
        if category not in self.categories:
            return []
        
        category_data = self.categories[category]
        
        if subcategory:
            # Get files from subcategory
            subcats = category_data.get('subcategories', {})
            return subcats.get(subcategory, [])
        else:
            # Get files from main category (if it has a 'files' list)
            if 'files' in category_data:
                return category_data['files']
            else:
                # Category only has subcategories, return all files from all subcats
                all_files = []
                subcats = category_data.get('subcategories', {})
                for files in subcats.values():
                    all_files.extend(files)
                return all_files
    
    def get_all_categories(self) -> List[str]:
        """Get list of all category names."""
        return list(self.categories.keys())
    
    def get_subcategories(self, category: str) -> List[str]:
        """Get list of subcategory names for a category."""
        if category not in self.categories:
            return []
        return list(self.categories[category].get('subcategories', {}).keys())
    
    def get_file_metadata(self, filename: str) -> Optional[FileMetadata]:
        """Get metadata for a specific file."""
        if filename not in self.files:
            return None
        
        data = self.files[filename]
        return FileMetadata(
            category=data.get('category', 'unknown'),
            subcategory=data.get('subcategory'),
            last_viewed=data.get('last_viewed'),
            size_bytes=data.get('size_bytes')
        )
