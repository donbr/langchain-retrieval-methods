#!/usr/bin/env python3
"""
Main retrieval application that uses existing data in Redis and Qdrant.
This assumes ingestion has already been completed separately.
"""

import os
from dotenv import load_dotenv

from langchain_qdrant import QdrantVectorStore
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.retrievers import ParentDocumentRetriever
from langchain_community.storage import RedisStore
from langchain.storage import create_kv_docstore
from qdrant_client import QdrantClient

# Load environment variables
load_dotenv()

class RetrievalApplication:
    def __init__(self):
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        self.setup_retriever()
    
    def setup_retriever(self):
        """Initialize ParentDocumentRetriever with existing data stores"""
        # Redis setup for parent documents
        redis_store = RedisStore(redis_url="redis://localhost:6379")
        parent_document_store = create_kv_docstore(redis_store)
        
        # Qdrant setup for child chunks
        qdrant_client = QdrantClient(
            url=os.getenv("QDRANT_API_URL"),
            api_key=os.getenv("QDRANT_API_KEY"),
            prefer_grpc=True
        )
        
        parent_children_vectorstore = QdrantVectorStore(
            embedding=self.embeddings,
            client=qdrant_client,
            collection_name="johnwick_parent_children",
        )
        
        # Initialize ParentDocumentRetriever WITHOUT calling add_documents
        # This leverages existing data in Redis and Qdrant
        child_splitter = RecursiveCharacterTextSplitter(chunk_size=200)
        self.parent_document_retriever = ParentDocumentRetriever(
            vectorstore=parent_children_vectorstore,
            docstore=parent_document_store,
            child_splitter=child_splitter,
        )
        
        # Validate that data exists
        self.validate_data_availability()
    
    def validate_data_availability(self):
        """Check if the required data exists in both stores"""
        try:
            # Check Redis
            redis_keys = list(self.parent_document_retriever.docstore.yield_keys())
            redis_count = len(redis_keys)
            
            # Check Qdrant  
            qdrant_count = self.parent_document_retriever.vectorstore.client.count(
                collection_name="johnwick_parent_children"
            ).count
            
            print(f"📊 Data Validation:")
            print(f"   Redis (parent docs): {redis_count} documents")
            print(f"   Qdrant (child chunks): {qdrant_count} vectors")
            
            if redis_count == 0 or qdrant_count == 0:
                raise ValueError(
                    "❌ No data found in stores. Please run ingestion.py first!"
                )
            
            print("✅ Data validation successful - ready for retrieval!")
            
        except Exception as e:
            print(f"❌ Data validation failed: {e}")
            print("💡 Make sure to run ingestion.py first to populate the data stores.")
            raise
    
    def query(self, question: str, k: int = 5):
        """Query the retriever for relevant documents"""
        try:
            # This works without calling add_documents because we're using existing data
            documents = self.parent_document_retriever.invoke(question)
            
            print(f"🔍 Query: {question}")
            print(f"📄 Retrieved {len(documents)} documents:")
            
            for i, doc in enumerate(documents[:k], 1):
                print(f"\n--- Document {i} ---")
                print(f"Content preview: {doc.page_content[:200]}...")
                print(f"Metadata: {doc.metadata}")
            
            return documents
            
        except Exception as e:
            print(f"❌ Query failed: {e}")
            return []

def main():
    """Main application entry point"""
    try:
        app = RetrievalApplication()
        
        # Example queries
        questions = [
            "Did people generally like John Wick?",
            "What do reviewers say about the action scenes?",
            "How do the John Wick movies compare to each other?"
        ]
        
        for question in questions:
            print("\n" + "="*60)
            app.query(question)
            
    except Exception as e:
        print(f"❌ Application failed to start: {e}")
        print("💡 Make sure Docker containers are running and ingestion.py has been executed.")

if __name__ == "__main__":
    main() 