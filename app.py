"""Notes Manager - Main Application."""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Optional
from nicegui import ui, app
from src.models import NotesData
from src.json_manager import JSONManager
from src.file_manager import FileManager
from src.search import SearchEngine
from src.embeddings import EmbeddingClient
from src.vector_store import VectorStore
from src.chunking import chunk_file
from dotenv import load_dotenv


logger = logging.getLogger('notes_manager')
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(name)s | %(message)s'
    )

# Load environment variables from .env (if present)
try:
    load_dotenv()
except Exception:
    # If dotenv not available or .env missing, continue silently
    pass


ARCHIVE_CATEGORY = 'Archived'


class NotesManager:
    """Main application class."""
    
    def __init__(self):
        # Load configuration
        self.load_config()
        
        # Initialize managers
        self.json_manager = JSONManager(
            self.json_path,
            self.backup_dir,
            self.config['max_backups']
        )
        self.file_manager = FileManager(
            self.notes_dir,
            self.config['file_extensions']
        )
        self.search_engine = SearchEngine()
        
        # Initialize semantic search components
        try:
            azure_config = self.config.get('azure_openai', {})
            self.embedding_client = EmbeddingClient(
                endpoint=azure_config.get('endpoint', ''),
                deployment_name=azure_config.get('deployment_name', 'text-embedding-3-small'),
                api_version=azure_config.get('api_version', '2024-02-01'),
                api_key=azure_config.get('api_key')  # Falls back to env var if None
            )
            
            vector_config = self.config.get('vector_store', {})
            self.vector_store = VectorStore(
                persist_directory=vector_config.get('persist_directory', './chroma_db'),
                collection_name=vector_config.get('collection_name', 'notes')
            )
            self.semantic_search_enabled = True
        except Exception as e:
            logger.warning(f"Semantic search disabled: {e}")
            self.embedding_client = None
            self.vector_store = None
            self.semantic_search_enabled = False
        
        # Load data
        self.reload_data()
        
        # UI state
        self.selected_file = None
        self.search_query = ''
        self.search_mode = 'filename'  # 'filename', 'fulltext', or 'semantic'
        self.selected_tree_node_id = None
        self.tree_nodes = []  # Store tree structure for lookups
        # Note: unindexed_count is set by reload_data() above
        
    def load_config(self):
        """Load configuration from config.json."""
        config_path = Path(__file__).parent / 'config.json'
        
        if not config_path.exists():
            raise FileNotFoundError("config.json not found. Please create it first.")
        
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        self.notes_dir = Path(self.config['notes_directory'])
        self.json_path = self.notes_dir / self.config['json_filename']
        self.backup_dir = Path(self.config['backup_directory'])
    
    def reload_data(self):
        """Reload all data from JSON."""
        try:
            raw_data = self.json_manager.load()
            self.data = NotesData(raw_data)

            # Find uncategorized files
            files_in_json = set(self.data.get_all_categorized_files())
            self.uncategorized = self.file_manager.find_uncategorized_files(files_in_json)

            # Update unindexed file count for semantic search
            if getattr(self, 'semantic_search_enabled', False) and getattr(self, 'vector_store', None):
                all_files = self.file_manager.find_all_note_files()
                unindexed = self.vector_store.get_unindexed_files(all_files)
                self.unindexed_count = len(unindexed)
                logger.info(f"Semantic search status: {len(all_files)} total files, {len(unindexed)} unindexed")
            else:
                self.unindexed_count = 0
                logger.info("Semantic search disabled or not initialized")

        except Exception as e:
            ui.notify(f"Error loading data: {e}", type='negative')
            raise
    
    def build_tree_data(self) -> List[dict]:
        """Build tree structure for ui.tree."""
        all_files = sorted(self.file_manager.find_all_note_files())

        tree_nodes = [
            {
                'id': 'all_files',
                'label': f"🌐 All files ({len(all_files)})",
                'icon': 'folder_special',
                'category': 'all_files',
            }
        ]
        
        # Add categorized files
        for category in self.data.get_all_categories():
            cat_data = self.data.categories[category]
            subcats = self.data.get_subcategories(category)
            
            node = {
                'id': category,
                'label': f"{category.replace('_', ' ').title()} ({cat_data.get('count', 0)})",
                'icon': 'folder',
                'category': category,
            }
            
            if subcats:
                # Category has subcategories
                node['children'] = []
                for subcat in subcats:
                    files = self.data.get_all_files_in_category(category, subcat)
                    subcat_node = {
                        'id': f"{category}/{subcat}",
                        'label': f"{subcat} ({len(files)})",
                        'icon': 'folder',
                        'category': category,
                        'subcategory': subcat,
                    }
                    node['children'].append(subcat_node)
            
            tree_nodes.append(node)
        
        # Add uncategorized section
        if self.uncategorized:
            tree_nodes.append({
                'id': 'uncategorized',
                'label': f"⚠️ Uncategorized ({len(self.uncategorized)})",
                'icon': 'warning',
                'category': 'uncategorized',
            })
        
        # Store for later lookups
        self.tree_nodes = tree_nodes
        return tree_nodes
    
    def find_node_by_id(self, node_id: str) -> dict:
        """Find a tree node by its ID."""
        def search_nodes(nodes, target_id):
            for node in nodes:
                if node['id'] == target_id:
                    return node
                if 'children' in node:
                    result = search_nodes(node['children'], target_id)
                    if result:
                        return result
            return None
        
        return search_nodes(self.tree_nodes, node_id)

    def find_node_by_label(self, node_label: str) -> Optional[dict]:
        """Find a tree node by its display label."""
        def search_nodes(nodes, target_label):
            for node in nodes:
                if node.get('label') == target_label:
                    return node
                if 'children' in node:
                    result = search_nodes(node['children'], target_label)
                    if result:
                        return result
            return None

        return search_nodes(self.tree_nodes, node_label)
    
    def get_files_for_selection(self, node_id: str) -> List[str]:
        """Get files for selected tree node."""
        if not node_id:
            return []
        
        # Find the node by ID
        selection = self.find_node_by_id(node_id)
        if not selection:
            return []
        
        category = selection.get('category')
        subcategory = selection.get('subcategory')
        
        if category == 'all_files':
            return sorted(self.file_manager.find_all_note_files())
        elif category == 'uncategorized':
            return self.uncategorized
        elif category:
            return self.data.get_all_files_in_category(category, subcategory)
        
        return []


# Global instance
notes_manager = None


@ui.page('/')
def main_page():
    """Main application page."""
    global notes_manager
    
    # Fix page overflow
    ui.query('body').style('margin: 0; padding: 0; overflow: hidden')
    ui.query('.nicegui-content').style('width: 100vw; max-width: none; height: 100vh; padding: 0; gap: 0')
    
    try:
        notes_manager = NotesManager()
    except Exception as e:
        ui.label(f"Error initializing app: {e}").classes('text-red')
        return
    
    # Header
    with ui.header().classes('items-center justify-between').style('height: 50px'):
        ui.label('📝 Notes Manager').classes('text-h5')
        with ui.row():
            ui.button(icon='refresh', on_click=lambda: refresh_app()).props('flat')
            ui.button(icon='settings', on_click=lambda: show_settings()).props('flat')
    
    # Main layout - 3 columns: tree | file list | note content
    with ui.element('div').style('width: 100vw; height: calc(100vh - 50px); overflow: hidden'):
        with ui.row().classes('w-full h-full').style('gap: 0'):
            with ui.column().classes('h-full p-2').style('width: 24%; min-width: 260px; overflow: hidden'):
                build_left_panel()

            with ui.column().classes('h-full p-2').style('width: 28%; min-width: 280px; overflow: hidden'):
                build_middle_panel()

            with ui.column().classes('h-full p-2').style('flex: 1; min-width: 360px; overflow: hidden'):
                build_right_panel()


def build_left_panel():
    """Build left navigation panel."""
    global search_input, search_mode_radio, file_tree, stats_label
    
    with ui.column().classes('w-full h-full p-2'):
        # Search box
        with ui.column().classes('w-full').style('gap: 8px'):
            search_input = ui.input(
                placeholder='Search files...',
                on_change=lambda e: on_search_change(e.value)
            ).props('outlined dense').classes('w-full')
            search_input.props('clearable')
            search_input.on('keyup', lambda _: on_search_change(search_input.value))
            
            # Search mode radio buttons - use dict for options
            search_mode_radio = ui.radio(
                options={'filename': 'File name', 'fulltext': 'Full text', 'semantic': 'Semantic'},
                value=notes_manager.search_mode,
                on_change=lambda e: on_search_mode_change(e.value)
            ).props('inline dense').classes('text-sm')
            
            # Ingestion status badge and button (for semantic search)
            if notes_manager.semantic_search_enabled:
                with ui.row().classes('w-full items-center').style('gap: 8px'):
                    # Always show badge with appropriate message and color
                    badge_text = f"{notes_manager.unindexed_count} not indexed" if notes_manager.unindexed_count > 0 else "All indexed"
                    badge_color = 'orange' if notes_manager.unindexed_count > 0 else 'green'
                    ingestion_badge = ui.badge(badge_text, color=badge_color)
                    
                    # Only show index button when there are unindexed files
                    if notes_manager.unindexed_count > 0:
                        ingestion_button = ui.button(
                            'Index now',
                            icon='download',
                            on_click=lambda: ingest_unindexed_files()
                        ).props('flat dense size=sm')
        
        ui.separator()
        
        # Category tree
        tree_data = notes_manager.build_tree_data()
        file_tree = ui.tree(
            tree_data,
            node_key='id',
            label_key='label',
            on_select=lambda e: on_tree_select(e.value)
        ).classes('w-full')
        file_tree.props('dense')
        
        ui.space()
        
        # Statistics
        with ui.card().classes('w-full'):
            ui.label('📊 Statistics').classes('text-subtitle2 font-bold')
            total_files = notes_manager.data.summary.get('total_files', 0)
            stats_label = ui.label(
                f"Total files: {total_files}\n"
                f"Uncategorized: {len(notes_manager.uncategorized)}"
            ).classes('text-caption')


def build_middle_panel():
    """Build middle panel for file list."""
    global file_list_container, file_info_label

    with ui.column().classes('w-full h-full p-2 gap-2'):
        file_info_label = ui.label('Select a category to view files').classes('text-h6')

        ui.separator()

        with ui.scroll_area().classes('w-full').style('height: 100%'):
            file_list_container = ui.column().classes('w-full')


def build_right_panel():
    """Build right panel for note content."""
    global content_viewer, note_title_label, note_category_label, action_buttons
    
    with ui.column().classes('w-full h-full p-2 gap-2'):
        note_title_label = ui.label('Select a file to view content').classes('text-h6')
        note_category_label = ui.label('').classes('text-caption text-grey-7')
        
        ui.separator()

        # Content viewer section
        with ui.column().classes('w-full').style('flex: 1; min-height: 0'):
            action_buttons = ui.row().classes('gap-2 mb-2')
            action_buttons.set_visibility(False)

            with ui.scroll_area().classes('w-full border').style('height: 100%'):
                content_viewer = ui.markdown('').classes('p-4')


def normalize_tree_selection(selection) -> Optional[str]:
    """Normalize tree selection payload to a node ID string."""
    if not selection:
        return None

    if isinstance(selection, str):
        return selection

    if isinstance(selection, dict):
        return selection.get('id')

    if isinstance(selection, (list, tuple, set)):
        first_item = next(iter(selection), None)
        return normalize_tree_selection(first_item)

    return str(selection)


def resolve_selected_node(selection) -> Optional[dict]:
    """Resolve selected tree payload to a known node from tree data."""
    if selection is None:
        return None

    if isinstance(selection, dict):
        node_id = selection.get('id')
        if node_id:
            node = notes_manager.find_node_by_id(node_id)
            if node:
                return node

        node_label = selection.get('label')
        if node_label:
            return notes_manager.find_node_by_label(node_label)

        return None

    if isinstance(selection, (list, tuple, set)):
        first_item = next(iter(selection), None)
        return resolve_selected_node(first_item)

    node_key = normalize_tree_selection(selection)
    if not node_key:
        return None

    return notes_manager.find_node_by_id(node_key) or notes_manager.find_node_by_label(node_key)


def on_tree_select(selection, reset_detail_panel: bool = True):
    """Handle tree node selection."""
    logger.info('Tree selection payload: %r', selection)

    selected_node = resolve_selected_node(selection)
    if not selected_node:
        logger.warning('Could not resolve selected tree node from payload: %r', selection)
        return
    
    # Get files for this selection
    node_id = selected_node.get('id')
    notes_manager.selected_tree_node_id = node_id
    files = notes_manager.get_files_for_selection(node_id)
    logger.info(
        'Tree node clicked: id=%s, category=%s, subcategory=%s, files_before_filter=%d',
        node_id,
        selected_node.get('category'),
        selected_node.get('subcategory'),
        len(files),
    )
    
    # Update file info
    category = selected_node.get('category', '')
    subcategory = selected_node.get('subcategory')
    
    if category == 'all_files':
        file_info_label.set_text(f"🌐 All files ({len(files)} files)")
    elif subcategory:
        file_info_label.set_text(f"📁 {category} / {subcategory} ({len(files)} files)")
    else:
        file_info_label.set_text(f"📁 {category.replace('_', ' ').title()} ({len(files)} files)")
    
    # Update file list
    display_file_list(files, category, subcategory)

    if reset_detail_panel:
        # Reset right panel when category changes
        notes_manager.selected_file = None
        note_title_label.set_text('Select a file to view content')
        note_category_label.set_text('')
        content_viewer.set_content('')
        action_buttons.clear()
        action_buttons.set_visibility(False)


def display_file_list(files: List[str], category: str, subcategory: str = None):
    """Display list of files."""
    file_list_container.clear()

    original_count = len(files)
    
    # Apply search filter if active
    files = apply_search_filter(files)

    logger.info(
        'Display file list: category=%s, subcategory=%s, files_total=%d, files_after_search=%d, search_query=%r',
        category,
        subcategory,
        original_count,
        len(files),
        notes_manager.search_query,
    )
    
    if not files:
        with file_list_container:
            ui.label('No files found').classes('text-grey')
        return
    
    # Create clickable list of files
    with file_list_container:
        with ui.list().props('dense bordered separator').classes('w-full'):
            for filename in files:
                with ui.item(on_click=lambda f=filename, c=category, s=subcategory: select_file(f, c, s)):
                    with ui.item_section().props('avatar'):
                        ui.icon('description')
                    with ui.item_section():
                        ui.item_label(filename)
                        # Show file size
                        size = notes_manager.file_manager.get_file_size(filename)
                        size_kb = size / 1024
                        ui.item_label(f'{size_kb:.1f} KB').props('caption')


def select_file(filename: str, category: str, subcategory: str = None):
    """Select and display a file."""
    effective_category = category
    effective_subcategory = subcategory

    if category == 'all_files':
        file_metadata = notes_manager.data.get_file_metadata(filename)
        if file_metadata:
            effective_category = file_metadata.category
            effective_subcategory = file_metadata.subcategory
        else:
            effective_category = 'uncategorized'
            effective_subcategory = None

    notes_manager.selected_file = filename
    notes_manager.selected_category = effective_category
    notes_manager.selected_subcategory = effective_subcategory
    
    # Load and display content
    try:
        content = notes_manager.file_manager.read_file_content(filename)
        
        # Update content viewer
        content_viewer.set_content(f"```\n{content}\n```")
        
        # Update note info
        note_title_label.set_text(f"📄 {filename}")
        category_text = f"Category: {effective_category}"
        if effective_subcategory:
            category_text += f" / {effective_subcategory}"
        note_category_label.set_text(category_text)
        
        # Show action buttons
        show_action_buttons(filename, effective_category, effective_subcategory)
        
    except Exception as e:
        ui.notify(f"Error reading file: {e}", type='negative')


def show_action_buttons(filename: str, current_category: str, current_subcategory: str = None):
    """Show action buttons for selected file."""
    action_buttons.clear()
    action_buttons.set_visibility(True)
    
    with action_buttons:
        if current_category != ARCHIVE_CATEGORY:
            ui.button(
                'Archive',
                icon='archive',
                on_click=lambda: archive_file(filename, current_category, current_subcategory)
            ).props('outline color=orange')

        # Move to category dropdown
        categories = notes_manager.data.get_all_categories()
        
        # Filter out current category
        other_categories = [c for c in categories if c != current_category]
        
        if other_categories:
            ui.select(
                label='Move to category',
                options=other_categories,
                on_change=lambda e: move_file_to_category(filename, current_category, current_subcategory, e.value)
            ).props('outlined dense').classes('w-64')
        
        # Open in external editor
        ui.button(
            'Open in Editor',
            icon='open_in_new',
            on_click=lambda: open_external(filename)
        ).props('outline')


def archive_file(filename: str, from_category: str, from_subcategory: str = None):
    """Move file to the dedicated archive category."""
    move_file_to_category(filename, from_category, from_subcategory, ARCHIVE_CATEGORY)


def move_file_to_category(filename: str, from_category: str, from_subcategory: str, to_category: str):
    """Move file to different category."""
    try:
        selected_node_id = notes_manager.selected_tree_node_id
        pre_move_visible_files = []
        if selected_node_id:
            pre_move_visible_files = notes_manager.get_files_for_selection(selected_node_id)
            pre_move_visible_files = apply_search_filter(pre_move_visible_files)

        next_candidate = None
        if filename in pre_move_visible_files:
            current_index = pre_move_visible_files.index(filename)
            remaining_files = [f for f in pre_move_visible_files if f != filename]
            if remaining_files:
                next_index = min(current_index, len(remaining_files) - 1)
                next_candidate = remaining_files[next_index]

        # Update data
        notes_manager.data.raw_data = notes_manager.file_manager.move_file_between_categories(
            filename,
            from_category,
            to_category,
            from_subcategory,
            None,  # to_subcategory (always None for now)
            notes_manager.data.raw_data
        )

        # Save changes (auto-repair stale files dict if sync drift blocks save)
        try:
            notes_manager.json_manager.save(notes_manager.data.raw_data)
        except ValueError as save_error:
            if 'Sync validation failed' not in str(save_error):
                raise

            notes_manager.data.raw_data = notes_manager.json_manager.rebuild_files_dict(notes_manager.data.raw_data)
            notes_manager.json_manager.save(notes_manager.data.raw_data)
            ui.notify('JSON sync drift detected and repaired automatically.', type='warning')
        
        ui.notify(f"Moved '{filename}' to '{to_category}'", type='positive')

        notes_manager.reload_data()

        file_tree._props['nodes'] = notes_manager.build_tree_data()
        file_tree.update()

        if selected_node_id:
            on_tree_select(selected_node_id, reset_detail_panel=False)

            selected_node = notes_manager.find_node_by_id(selected_node_id)
            if selected_node:
                node_category = selected_node.get('category')
                node_subcategory = selected_node.get('subcategory')

                refreshed_visible_files = notes_manager.get_files_for_selection(selected_node_id)
                refreshed_visible_files = apply_search_filter(refreshed_visible_files)

                if filename in refreshed_visible_files:
                    select_file(filename, node_category, node_subcategory)
                elif next_candidate and next_candidate in refreshed_visible_files:
                    select_file(next_candidate, node_category, node_subcategory)
                elif refreshed_visible_files:
                    select_file(refreshed_visible_files[0], node_category, node_subcategory)
                else:
                    notes_manager.selected_file = None
                    note_title_label.set_text('No files in current view')
                    note_category_label.set_text('')
                    content_viewer.set_content('')
                    action_buttons.clear()
                    action_buttons.set_visibility(False)
        
    except Exception as e:
        ui.notify(f"Error moving file: {e}", type='negative')


def open_external(filename: str):
    """Open file in external editor."""
    try:
        notes_manager.file_manager.open_in_external_editor(filename)
        ui.notify(f"Opening {filename} in external editor", type='info')
    except Exception as e:
        ui.notify(f"Error opening file: {e}", type='negative')


def on_search_change(query: str):
    """Handle search query change."""
    notes_manager.search_query = (query or '').strip()

    selected_node_id = notes_manager.selected_tree_node_id
    if selected_node_id:
        on_tree_select(selected_node_id, reset_detail_panel=False)
        return

    # Fallback for cases where tree selection exists but wasn't persisted yet
    tree_value = getattr(file_tree, 'value', None)
    if tree_value:
        on_tree_select(tree_value, reset_detail_panel=False)


def on_search_mode_change(mode: str):
    """Handle search mode change (filename, fulltext, or semantic)."""
    notes_manager.search_mode = mode
    on_search_change(notes_manager.search_query)


def apply_search_filter(files: List[str]) -> List[str]:
    """Apply current search settings to file list."""
    query = notes_manager.search_query
    if not query:
        return files

    mode = notes_manager.search_mode
    
    if mode == 'semantic':
        if notes_manager.semantic_search_enabled:
            return notes_manager.search_engine.search_semantic(
                files,
                query,
                notes_manager.vector_store,
                notes_manager.embedding_client
            )
        else:
            # Fallback to filename search if semantic not available
            ui.notify('Semantic search not available. Using filename search.', type='warning')
            return notes_manager.search_engine.search_filenames(files, query)
    
    elif mode == 'fulltext':
        return notes_manager.search_engine.search_filenames_or_content(
            files,
            query,
            notes_manager.file_manager.read_file_content,
        )
    
    else:  # mode == 'filename'
        return notes_manager.search_engine.search_filenames(files, query)


async def ingest_unindexed_files():
    """Ingest files that are not yet in the vector database."""
    if not notes_manager.semantic_search_enabled:
        ui.notify('Semantic search is not enabled.', type='warning')
        return
    
    try:
        # Get unindexed files
        all_files = notes_manager.file_manager.find_all_note_files()
        unindexed = notes_manager.vector_store.get_unindexed_files(all_files)
        
        if not unindexed:
            ui.notify('All files are already indexed.', type='info')
            return
        
        file_count = len(unindexed)
        ui.notify(f'Indexing {file_count} files...', type='info')
        
        # Get chunking config
        vector_config = notes_manager.config.get('vector_store', {})
        chunk_min = vector_config.get('chunk_min_chars', 100)
        chunk_max = vector_config.get('chunk_max_chars', 500)
        
        indexed_count = 0
        for filename in unindexed:
            try:
                # Read file content
                content = notes_manager.file_manager.read_file_content(filename)
                
                # Chunk the file
                chunks = chunk_file(filename, content, chunk_min, chunk_max)
                
                if not chunks:
                    continue
                
                # Generate embeddings for all chunks
                chunk_texts = [chunk.text for chunk in chunks]
                embeddings = notes_manager.embedding_client.embed_texts(chunk_texts)
                
                # Ingest into vector store
                notes_manager.vector_store.ingest_file(filename, chunks, embeddings)
                indexed_count += 1
                
                # Update UI periodically (every 10 files)
                if indexed_count % 10 == 0:
                    ui.notify(f'Indexed {indexed_count}/{file_count} files...', type='info')
                
            except Exception as e:
                logger.error(f"Error indexing {filename}: {e}")
                continue
        
        # Update the unindexed count and reload to refresh badge
        notes_manager.unindexed_count = 0
        
        ui.notify(f'Successfully indexed {indexed_count} files!', type='positive')
        
        # Reload data to refresh the badge display
        notes_manager.reload_data()
        
    except Exception as e:
        logger.error(f"Ingestion error: {e}")
        ui.notify(f'Error during indexing: {e}', type='negative')


def refresh_app():
    """Refresh the entire application."""
    ui.notify('Refreshing...', type='info')
    notes_manager.reload_data()
    ui.navigate.reload()


def show_settings():
    """Show settings dialog."""
    with ui.dialog() as dialog, ui.card():
        ui.label('Settings').classes('text-h6')
        
        with ui.column().classes('gap-4 w-96'):
            ui.label(f"Notes directory: {notes_manager.notes_dir}").classes('text-caption')
            ui.label(f"JSON file: {notes_manager.json_path}").classes('text-caption')
            ui.label(f"Backup directory: {notes_manager.backup_dir}").classes('text-caption')
            
            ui.separator()
            
            # Validation
            if ui.button('Validate JSON Sync', on_click=lambda: validate_json(dialog)):
                pass
            
            ui.separator()
            
            ui.button('Close', on_click=dialog.close)
    
    dialog.open()


def validate_json(dialog):
    """Validate JSON sync."""
    errors = notes_manager.json_manager.validate_sync(notes_manager.data.raw_data)
    
    if errors:
        ui.notify(f"Found {len(errors)} sync errors", type='warning')
        # Show first few errors
        for error in errors[:3]:
            ui.notify(error, type='warning')
    else:
        ui.notify("JSON sync validation passed!", type='positive')


if __name__ in {'__main__', '__mp_main__'}:
    ui.run(
        title='Notes Manager',
        port=8080,
        show=True,
        reload=False
    )
