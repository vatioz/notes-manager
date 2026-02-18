"""JSON management: load, save, backup, and sync validation."""

import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Tuple


class JSONManager:
    """Manages JSON data operations including backup and validation."""
    
    def __init__(self, json_path: Path, backup_dir: Path, max_backups: int = 5):
        self.json_path = json_path
        self.backup_dir = backup_dir
        self.max_backups = max_backups
        
        # Ensure backup directory exists
        self.backup_dir.mkdir(parents=True, exist_ok=True)
    
    def load(self) -> Dict[str, Any]:
        """Load JSON data from file."""
        if not self.json_path.exists():
            raise FileNotFoundError(f"JSON file not found: {self.json_path}")
        
        with open(self.json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def save(self, data: Dict[str, Any]) -> None:
        """Save JSON with backup and validation."""
        # 1. Validate sync before saving
        errors = self.validate_sync(data)
        if errors:
            raise ValueError(f"Sync validation failed:\n" + "\n".join(errors[:5]))
        
        # 2. Create backup of current file
        if self.json_path.exists():
            self._create_backup()
        
        # 3. Write to temporary file first
        temp_path = self.json_path.with_suffix('.json.tmp')
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        # 4. Verify temp file is valid JSON
        with open(temp_path, 'r', encoding='utf-8') as f:
            json.load(f)  # Will raise if invalid
        
        # 5. Replace original with temp
        shutil.move(str(temp_path), str(self.json_path))
        
        # 6. Update metadata
        data['metadata']['last_modified'] = datetime.now().isoformat()
        
        # 7. Clean old backups
        self._cleanup_old_backups()
    
    def _create_backup(self) -> None:
        """Create a timestamped backup of the JSON file."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"{self.json_path.stem}_{timestamp}{self.json_path.suffix}"
        backup_path = self.backup_dir / backup_name
        
        shutil.copy(self.json_path, backup_path)
    
    def _cleanup_old_backups(self) -> None:
        """Remove old backups, keeping only max_backups most recent."""
        backups = sorted(
            self.backup_dir.glob(f"{self.json_path.stem}_*{self.json_path.suffix}"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        
        # Remove old backups
        for old_backup in backups[self.max_backups:]:
            old_backup.unlink()
    
    def validate_sync(self, data: Dict[str, Any]) -> List[str]:
        """
        Validate that files dict and categories are in sync.
        Returns list of error messages (empty if valid).
        """
        errors = []
        categories = data.get('categories', {})
        files_dict = data.get('files', {})
        
        # Track all files found in categories
        files_in_categories = set()
        
        # Check each category
        for category_name, category_data in categories.items():
            # Check files in main category
            if 'files' in category_data:
                for filename in category_data['files']:
                    files_in_categories.add(filename)
                    
                    # Check if file exists in files dict
                    if filename not in files_dict:
                        errors.append(
                            f"File '{filename}' in category '{category_name}' "
                            f"but not in files dict"
                        )
                    else:
                        # Check if category matches
                        if files_dict[filename].get('category') != category_name:
                            errors.append(
                                f"File '{filename}' category mismatch: "
                                f"in category '{category_name}' but files dict says "
                                f"'{files_dict[filename].get('category')}'"
                            )
            
            # Check subcategories
            if 'subcategories' in category_data:
                for subcat_name, file_list in category_data['subcategories'].items():
                    for filename in file_list:
                        files_in_categories.add(filename)
                        
                        # Check if file exists in files dict
                        if filename not in files_dict:
                            errors.append(
                                f"File '{filename}' in {category_name}/{subcat_name} "
                                f"but not in files dict"
                            )
                        else:
                            # Check if category and subcategory match
                            file_meta = files_dict[filename]
                            if file_meta.get('category') != category_name:
                                errors.append(
                                    f"File '{filename}' category mismatch in subcategory"
                                )
                            if file_meta.get('subcategory') != subcat_name:
                                errors.append(
                                    f"File '{filename}' subcategory mismatch: "
                                    f"in '{subcat_name}' but files dict says "
                                    f"'{file_meta.get('subcategory')}'"
                                )
        
        # Check that all files in files_dict are in categories
        for filename in files_dict.keys():
            if filename not in files_in_categories:
                errors.append(
                    f"File '{filename}' in files dict but not found in any category"
                )
        
        return errors
    
    def rebuild_files_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Rebuild files dict from categories (use when sync is broken).
        Returns updated data.
        """
        new_files_dict = {}
        categories = data.get('categories', {})
        
        for category_name, category_data in categories.items():
            # Process files in main category
            if 'files' in category_data:
                for filename in category_data['files']:
                    new_files_dict[filename] = {
                        'category': category_name,
                        'subcategory': None
                    }
            
            # Process subcategories
            if 'subcategories' in category_data:
                for subcat_name, file_list in category_data['subcategories'].items():
                    for filename in file_list:
                        new_files_dict[filename] = {
                            'category': category_name,
                            'subcategory': subcat_name
                        }
        
        data['files'] = new_files_dict
        return data
