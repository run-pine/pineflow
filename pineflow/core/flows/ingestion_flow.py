
from enum import Enum
from typing import List, Optional

from pineflow.core.document.schema import Document, TransformerComponent
from pineflow.core.readers.base import BaseReader
from pineflow.core.vector_stores.base import BaseVectorStore

class DedupStage(Enum):
    """
    Document de-duplication stages determine when the deduplication process occurs during the ingestion flow.
    """
    PRE_TRANSFORM = "pre_transform"
    POST_TRANSFORM = "post_transform"
    
class DedupStrategy(Enum):
    """
    Document de-duplication strategies work by comparing the hashes in the vector store. 
    They require a vector store to be set.
    """
    DUPLICATE_ONLY = "duplicate_only"
    DUPLICATE_AND_DELETE = "duplicate_and_delete"
    DEDUPLICATE_OFF = "deduplicate_off"

class IngestionFlow():
    """An ingestion flow for processing and storing data.

    Args:
        transformers (List[TransformerComponent]): A list of transformer components applied to the input documents.
        dedup_stage (DedupStage): The stage at which deduplication is applied (before or after transformation). 
                                 Defaults to ``DedupStage.PRE_TRANSFORM``.
        dedup_strategy (str): The strategy used for handling duplicates. Defaults to ``DedupStrategy.DUPLICATE_ONLY``.
        readers (BaseReader, optional): List of readers for loading or fetching documents.
        vector_store (BaseVectorStore, optional): Vector store for saving processed documents

    Example:
        .. code-block:: python

            from pineflow.core.flows import IngestionFlow
            from pineflow.core.text_chunkers import TokenTextChunker
            from pineflow.embeddings.huggingface import HuggingFaceEmbedding

            ingestion_flow = IngestionFlow(
                transformers=[
                    TokenTextChunker(),
                    HuggingFaceEmbedding(model_name="intfloat/multilingual-e5-small"),
                ]
            )
    """

    def __init__(self, 
                 transformers: List[TransformerComponent],
                 dedup_stage: DedupStage = DedupStage.PRE_TRANSFORM,
                 dedup_strategy: DedupStrategy = DedupStrategy.DUPLICATE_ONLY,
                 readers: Optional[List[BaseReader]] = None,
                 vector_store: Optional[BaseVectorStore] = None
                 ) -> None:
        
        self.readers = readers
        self.dedup_stage = dedup_stage
        self.dedup_strategy = dedup_strategy
        self.transformers = transformers
        self.vector_store = vector_store
        
    def _read_documents(self, documents: Optional[List[Document]]):
        input_documents = []
        
        if documents is not None:
            input_documents.extend(documents)
            
        if self.readers is not None:
            for reader in self.readers:
                input_documents.extend(reader.load_data())
        
        return input_documents    
    
    def _handle_duplicates(self, documents) -> List[Document]:
        ids, existing_hashes, existing_ref_hashes = self.vector_store.get_all_document_hashes()
        if self.dedup_stage == DedupStage.PRE_TRANSFORM:
            # Fallback to document own hash if `ref_doc_hash` (parent level) is missing for de-duplication
            hashes_fallback = [existing_ref_hashes[i] if existing_ref_hashes[i] is not None else existing_hashes[i] 
                                        for i in range(len(existing_ref_hashes))]
        elif self.dedup_stage == DedupStage.POST_TRANSFORM:
            # Use own document hash (chunks level) for de-duplication
            hashes_fallback = existing_hashes
            
        current_hashes = []
        current_unique_hashes = []
        dedup_documents_to_run = []

        for doc in documents:
            current_hashes.append(doc.hash)

            if (doc.hash not in hashes_fallback and 
                doc.hash not in current_unique_hashes and 
                doc.get_content() != ""):
                dedup_documents_to_run.append(doc)
                current_unique_hashes.append(doc.hash) # Prevent duplicating same document hash in same batch flow execution.
        
        if self.dedup_strategy == DedupStrategy.DUPLICATE_AND_DELETE:
            ids_to_remove = [ids[i] for i in range(len(hashes_fallback)) 
                           if hashes_fallback[i] not in current_hashes]
 
            if self.vector_store is not None:
                self.vector_store.delete_documents(ids_to_remove)

        return dedup_documents_to_run
                
    def _run_transformers(self, documents: List[Document], transformers: TransformerComponent) -> List[Document]:
        _documents = documents.copy()
        
        for transform in transformers:
            _documents = transform(_documents)
        
        return _documents    
    
    def run(self, documents: List[Document]=None) -> List[Document]:
        """Run an ingestion flow.

        Args:
            documents: Set of documents to be transformed.

        Example:
            .. code-block:: python

                ingestion_flow.run(documents: List[Document])
        """
        input_documents = self._read_documents(documents)
        
        # Apply pre-transform de-dup (parent level)
        if (self.vector_store is not None and 
            self.dedup_strategy != DedupStrategy.DEDUPLICATE_OFF and
            self.dedup_stage == DedupStage.PRE_TRANSFORM):
            
            documents_to_run = self._handle_duplicates(input_documents)
        else:
            documents_to_run = input_documents
        
        if documents_to_run:
            documents = self._run_transformers(documents_to_run, self.transformers)

            documents = documents or []
            
            # Apply post-transform de-dup (chunk level)
            if (self.vector_store is not None and
            self.dedup_strategy != DedupStrategy.DEDUPLICATE_OFF and
            self.dedup_stage == DedupStage.POST_TRANSFORM):
                documents = self._handle_duplicates(documents)
            
            if self.vector_store is not None and documents:
                self.vector_store.add_documents(documents)
        
        return documents
