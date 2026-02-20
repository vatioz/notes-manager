"""
LanceDB vector store wrapper for semantic search over note files.
"""
from dataclasses import dataclass
from typing import List, Set, Optional
import os

# Make lancedb import resilient
LANCEDB_AVAILABLE = True
LANCEDB_IMPORT_ERROR = None
try:
    import lancedb
except Exception as e:
    LANCEDB_AVAILABLE = False
    LANCEDB_IMPORT_ERROR = e


@dataclass
class SearchResult:
    """Represents a semantic search result."""
    filename: str
    text: str
    distance: float
    line_start: int
    line_end: int


class VectorStore:
    """Vector database wrapper using LanceDB for note embeddings."""
    
    def __init__(self, persist_directory: str, collection_name: str = "notes"):
        """
        Initialize LanceDB vector store.
        
        Args:
            persist_directory: Directory to persist the LanceDB database
            collection_name: Name of the table to use
        """
        self.persist_directory = persist_directory
        self.collection_name = collection_name

        if not LANCEDB_AVAILABLE:
            raise RuntimeError(f"LanceDB is not available: {LANCEDB_IMPORT_ERROR}")

        # Create directory if it doesn't exist
        os.makedirs(persist_directory, exist_ok=True)

        # Initialize LanceDB client
        self.db = lancedb.connect(persist_directory)
        
        # Check if table exists by listing table names
        self.table = None
        try:
            existing_tables = self.db.table_names()
            if collection_name in existing_tables:
                self.table = self.db.open_table(collection_name)
                print(f"VectorStore: Opened existing table '{collection_name}'")
            else:
                print(f"VectorStore: Table '{collection_name}' does not exist yet, will be created on first ingest")
        except Exception as e:
            print(f"VectorStore: Error checking/opening table: {e}")
    
    def get_ingested_files(self) -> Set[str]:
        """
        Get the set of filenames that have been ingested into the vector store.
        
        Returns:
            Set of filenames that exist in the database
        """
        if self.table is None:
            print("VectorStore: Table is None, returning empty set")
            return set()
        
        try:
            # Query all records and extract unique filenames (limit to max count)
            # LanceDB requires search query to get data, so we do a dummy search
            results = self.table.search().limit(100000).to_list()
            if not results:
                print("VectorStore: Table is empty, returning empty set")
                return set()
            
            filenames = set(row['filename'] for row in results if 'filename' in row)
            print(f"VectorStore: Found {len(filenames)} ingested files")
            return filenames
        except Exception as e:
            print(f"Error getting ingested files: {e}")
            return set()
    
    def get_unindexed_files(self, all_files: Set[str]) -> Set[str]:
        """
        Get files that exist on disk but are not in the vector store.
        
        Args:
            all_files: Set of all filenames from disk
        
        Returns:
            Set of filenames not yet ingested
        """
        ingested = self.get_ingested_files()
        unindexed = all_files - ingested
        print(f"VectorStore: {len(all_files)} total files, {len(ingested)} ingested, {len(unindexed)} unindexed")
        return unindexed
    
    def ingest_file(self, filename: str, chunks: List, embeddings: List[List[float]]):
        """
        Ingest a file's chunks into the vector store.
        
        Deletes any existing chunks for this file first (to support re-ingestion).
        
        Args:
            filename: Name of the file being ingested
            chunks: List of Chunk objects from chunking.py
            embeddings: List of embedding vectors (one per chunk)
        """
        if not chunks or not embeddings:
            return
        
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"Chunk count ({len(chunks)}) doesn't match embedding count ({len(embeddings)})"
            )
        
        # Delete existing chunks for this file
        self.delete_file(filename)
        
        # Prepare data for LanceDB (list of dicts)
        records = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            records.append({
                'id': f"{filename}_{i}",
                'filename': chunk.filename,
                'text': chunk.text,
                'line_start': chunk.line_start,
                'line_end': chunk.line_end,
                'vector': embedding
            })
        
        # Add to table (create if doesn't exist)
        if self.table is None:
            self.table = self.db.create_table(self.collection_name, records)
        else:
            self.table.add(records)
    
    def delete_file(self, filename: str):
        """
        Delete all chunks for a given file from the vector store.
        
        Args:
            filename: Name of the file to remove
        """
        if self.table is None:
            return
        
        try:
            # LanceDB uses SQL-like delete syntax
            self.table.delete(f"filename = '{filename}'")
        except Exception as e:
            # If table doesn't exist or filename not found, silently continue
            pass
    
    def search(
        self,
        query_embedding: List[float],
        n_results: int = 20,
        filter_filenames: Optional[List[str]] = None
    ) -> List[SearchResult]:
        """
        Search for similar chunks using semantic similarity.
        
        Args:
            query_embedding: Embedding vector of the search query
            n_results: Maximum number of results to return
            filter_filenames: Optional list of filenames to restrict search to
        
        Returns:
            List of SearchResult objects, ranked by similarity
        """
        if self.table is None:
            return []
        
        try:
            # Build where filter if filenames provided
            where = None
            if filter_filenames:
                # LanceDB uses SQL-like where clause
                if len(filter_filenames) == 1:
                    where = f"filename = '{filter_filenames[0]}'"
                else:
                    # Create IN clause
                    filenames_str = "', '".join(filter_filenames)
                    where = f"filename IN ('{filenames_str}')"
            
            # Query LanceDB
            query = self.table.search(query_embedding).limit(n_results)
            if where:
                query = query.where(where)
            
            results = query.to_list()
            
            if not results:
                return []
            
            # Convert to SearchResult objects
            search_results = []
            for result in results:
                search_results.append(SearchResult(
                    filename=result['filename'],
                    text=result['text'],
                    distance=result['_distance'],
                    line_start=result['line_start'],
                    line_end=result['line_end']
                ))
            
            return search_results
        
        except Exception as e:
            print(f"Error during semantic search: {e}")
            return []
    
    def get_stats(self) -> dict:
        """
        Get statistics about the vector store.
        
        Returns:
            Dictionary with 'total_chunks' and 'unique_files' counts
        """
        if self.table is None:
            return {'total_chunks': 0, 'unique_files': 0}
        
        try:
            results = self.table.search().limit(100000).to_list()
            total_chunks = len(results)
            unique_files = len(set(row['filename'] for row in results if 'filename' in row))
            
            return {
                'total_chunks': total_chunks,
                'unique_files': unique_files
            }
        except Exception as e:
            print(f"Error getting stats: {e}")
            return {'total_chunks': 0, 'unique_files': 0}
