# Notes Manager

A web-based application for managing and categorizing notes built with NiceGUI.

## Features

- 📁 Browse notes by category and subcategory
- 🔍 Search files by name
- 📄 View file contents (read-only)
- 🔄 Move files between categories
- ⚠️ Detect uncategorized files
- 💾 Automatic JSON backup before saves
- ✅ JSON sync validation

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure the notes directory in `config.json`:
```json
{
  "notes_directory": "C:\\path\\to\\your\\notes"
}
```

3. Run the application:
```bash
python app.py
```

4. Open your browser to `http://localhost:8080`

## Usage

### Navigation
- Click on categories in the left panel to view files
- Click on a file to view its content
- Use the search box to filter files by name

### Moving Files
1. Select a file
2. Use the "Move to category" dropdown
3. Select destination category
4. File is moved automatically

### Uncategorized Files
- Files not in the JSON will appear in the "Uncategorized" section
- Select them and move to appropriate categories

### Settings
- Click the settings icon to validate JSON sync
- View configuration details

## Project Structure

```
notes-manager/
├── app.py              # Main application
├── config.json         # Configuration
├── requirements.txt    # Dependencies
├── src/
│   ├── models.py       # Data models
│   ├── json_manager.py # JSON operations
│   ├── file_manager.py # File operations
│   └── search.py       # Search functionality
└── backups/            # Automatic backups
```

## Configuration

Edit `config.json` to customize:
- `notes_directory`: Path to your notes folder
- `json_filename`: Name of the categorization JSON file
- `max_backups`: Number of backups to keep
- `file_extensions`: Valid note file extensions

## License

MIT
