"""File operations: detection, reading, and categorization."""

import os
from pathlib import Path
from typing import List, Set, Optional


class FileManager:
    """Manages file system operations for notes."""
    
    def __init__(self, notes_dir: Path, file_extensions: List[str]):
        self.notes_dir = Path(notes_dir)
        self.file_extensions = file_extensions
    
    def find_all_note_files(self) -> Set[str]:
        """Find all note files in the notes directory."""
        all_files = set()
        
        for ext in self.file_extensions:
            # Find files with this extension
            files = self.notes_dir.glob(f"*{ext}")
            all_files.update(f.name for f in files if f.is_file())
        
        return all_files
    
    def find_uncategorized_files(self, files_in_json: Set[str]) -> List[str]:
        """
        Find files that exist on disk but are not in JSON.
        Returns sorted list of uncategorized filenames.
        """
        all_files = self.find_all_note_files()
        uncategorized = all_files - files_in_json
        
        # Exclude the JSON file itself
        uncategorized.discard('notes_categorization.json')
        
        return sorted(uncategorized)
    
    def read_file_content(self, filename: str) -> str:
        """Read and return file content."""
        file_path = self.notes_dir / filename
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {filename}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            # Try with different encoding
            with open(file_path, 'r', encoding='latin-1') as f:
                return f.read()
    
    def get_file_size(self, filename: str) -> int:
        """Get file size in bytes."""
        file_path = self.notes_dir / filename
        if not file_path.exists():
            return 0
        return file_path.stat().st_size
    
    def open_in_external_editor(self, filename: str) -> None:
        """Open file in system default editor."""
        file_path = self.notes_dir / filename
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {filename}")
        
        # Use os.startfile on Windows
        os.startfile(str(file_path))
    
    def move_file_between_categories(
        self,
        filename: str,
        from_category: str,
        to_category: str,
        from_subcategory: Optional[str],
        to_subcategory: Optional[str],
        data: dict
    ) -> dict:
        """
        Move a file between categories (JSON only, no physical move).
        Returns updated data dict.
        """
        # 1. Update files dict
        if filename not in data['files']:
            data['files'][filename] = {}
        
        data['files'][filename]['category'] = to_category
        data['files'][filename]['subcategory'] = to_subcategory
        
        # 2. Remove from old location
        self._remove_from_category(data, filename, from_category, from_subcategory)
        
        # 3. Add to new location
        self._add_to_category(data, filename, to_category, to_subcategory)
        
        # 4. Update counts
        self._update_counts(data)
        
        return data
    
    def _remove_from_category(
        self,
        data: dict,
        filename: str,
        category: str,
        subcategory: Optional[str]
    ) -> None:
        """Remove file from category/subcategory."""
        if category not in data['categories']:
            return
        
        cat_data = data['categories'][category]
        
        if subcategory:
            # Remove from subcategory
            if 'subcategories' in cat_data and subcategory in cat_data['subcategories']:
                if filename in cat_data['subcategories'][subcategory]:
                    cat_data['subcategories'][subcategory].remove(filename)
        else:
            # Remove from main category files list
            if 'files' in cat_data and filename in cat_data['files']:
                cat_data['files'].remove(filename)
    
    def _add_to_category(
        self,
        data: dict,
        filename: str,
        category: str,
        subcategory: Optional[str]
    ) -> None:
        """Add file to category/subcategory."""
        if category not in data['categories']:
            # Create category if it doesn't exist
            data['categories'][category] = {
                'description': 'Custom category',
                'count': 0,
                'files': []
            }
        
        cat_data = data['categories'][category]
        
        if subcategory:
            # Add to subcategory
            if 'subcategories' not in cat_data:
                cat_data['subcategories'] = {}
            
            if subcategory not in cat_data['subcategories']:
                cat_data['subcategories'][subcategory] = []
            
            if filename not in cat_data['subcategories'][subcategory]:
                cat_data['subcategories'][subcategory].append(filename)
        else:
            # Add to main category files list
            if 'files' not in cat_data:
                cat_data['files'] = []
            
            if filename not in cat_data['files']:
                cat_data['files'].append(filename)
    
    def _update_counts(self, data: dict) -> None:
        """Update file counts for all categories."""
        for category_name, cat_data in data['categories'].items():
            count = 0
            
            # Count files in main category
            if 'files' in cat_data:
                count += len(cat_data['files'])
            
            # Count files in subcategories
            if 'subcategories' in cat_data:
                for file_list in cat_data['subcategories'].values():
                    count += len(file_list)
            
            cat_data['count'] = count
        
        # Update summary
        if 'summary' in data:
            total = sum(cat_data.get('count', 0) for cat_data in data['categories'].values())
            data['summary']['total_files'] = total
