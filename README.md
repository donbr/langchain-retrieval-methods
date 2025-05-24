# LangChain Retrieval Methods: Comprehensive Analysis

## Executive Summary

This analysis examines a systematic comparison of seven retrieval methods in LangChain using John Wick movie reviews as a test dataset. The study demonstrates how different retrieval strategies affect both the quality and focus of responses, revealing key insights about document chunking, search algorithms, and ensemble approaches in Retrieval-Augmented Generation (RAG) systems.

**Key Finding**: Each retrieval method provides different perspectives on the same question ("Did people generally like John Wick?"), with varying levels of detail, nuance, and temporal awareness across the movie series.

---

## Quickstart

To set up and run this project using [uv](https://github.com/astral-sh/uv):

```bash
# 1. Create a virtual environment (Python 3.11)
uv venv --python 3.11

# 2. Activate the virtual environment
# On Linux/macOS:
source .venv/bin/activate
# On Windows (Command Prompt):
.venv\Scripts\activate

# 3. Install dependencies
uv pip install -r requirements.txt
```

The main notebook is located at:

```
retrever_method_comparisonon.ipynb
```

## Key Concepts Explained

### 1. Vector Stores and Document Processing

The experiment uses **Qdrant Cloud** as the vector database, processing 100 John Wick movie reviews from 4 films. This demonstrates a **modern approach** where the baseline documents are loaded directly without chunking - a significant departure from historical RAG practices.

**Historical Context (Pre-2024)**: Traditional RAG systems almost always chunked documents before vectorization, as document loaders and text splitters were tightly coupled.

**Current Practice (2025)**: LangChain's CSVLoader now creates one document per row without automatic chunking, allowing for three distinct document organization strategies:

- **Baseline Collection**: 100 original documents (1:1 ratio, **no chunking**)
- **Parent Document Collection**: 4,817 documents (chunked with retrieval of full parents)  
- **Semantic Collection**: 179 documents (semantically-aware chunking)

### 2. Document Chunking Strategies

#### Traditional Chunking (When Applied)
- **RecursiveCharacterTextSplitter**: Fixed-size chunks (200 characters)
- Creates predictable, uniform segments
- May break semantic boundaries

#### **Document Loading Evolution**
- **Pre-2024**: Document loaders typically included automatic chunking parameters
- **2024-2025**: Clear separation between loading and chunking allows for:
  - Direct vectorization of complete documents (as shown in baseline)
  - Optional post-loading chunking strategies
  - Comparison of chunked vs non-chunked approaches

#### **Architectural Shift**
The notebook demonstrates a **paradigm shift** in RAG architecture:
- **Traditional**: Load → Chunk → Vectorize → Store
- **Modern**: Load → Vectorize → Store (with optional chunking strategies)

#### Semantic Chunking  
- **SemanticChunker**: Uses embeddings to find natural breakpoints
- Results in 179 semantically coherent chunks vs 4,817 traditional chunks
- Preserves meaning boundaries using "percentile" threshold

### 3. Embedding Strategy
- **Model**: OpenAI `text-embedding-3-small` (1536 dimensions)
- **Distance Metric**: Cosine similarity
- **Search Configuration**: Top-k retrieval (k=10 for most methods)

---

## Retrieval Methods Comparison

### 1. **Naive Retrieval** (Baseline - No Chunking)
- **Approach**: Direct vector similarity search on whole documents
- **Documents**: 100 baseline documents (one per CSV row)
- **Innovation**: Demonstrates modern practice of vectorizing complete documents
- **Historical Note**: Contrasts with pre-2024 practice where documents were almost always chunked before vectorization
- **Strength**: Simple, fast, direct semantic matching with full context preserved
- **Response Pattern**: Focused on positive reception, mentions style and action

### 2. **BM25 Retrieval** (Keyword-Based)
- **Approach**: Statistical ranking function (term frequency analysis)
- **Algorithm**: Okapi BM25 for keyword relevance
- **Strength**: Excellent keyword matching, handles exact terms well
- **Response Pattern**: More nuanced view across film series, notes mixed reception for later films

### 3. **Contextual Compression** (Reranked)
- **Approach**: Uses Cohere Rerank v3.0 to post-process results
- **Pipeline**: Retrieve → Rerank → Compress
- **Strength**: Filters irrelevant content, improves precision
- **Response Pattern**: Most comprehensive positive summary, highlights specific qualities

### 4. **Multi-Query Retrieval** (Query Expansion)
- **Approach**: LLM generates multiple query variations
- **Process**: Single question → Multiple perspectives → Unified results
- **Strength**: Captures different aspects of the same intent
- **Response Pattern**: Most detailed response with specific examples and ratings

### 5. **Parent Document Retrieval** (Hierarchical)
- **Approach**: Search small chunks (200 chars), return full parent documents
- **Documents**: 4,817 child chunks → 100 parent documents
- **Strength**: Precision of small chunks + context of full documents
- **Response Pattern**: Balanced view including both positive and negative opinions

### 6. **Ensemble Retrieval** (Hybrid)
- **Approach**: Combines 5 retrievers with equal weights (0.2 each)
- **Fusion**: Reciprocal Rank Fusion algorithm
- **Components**: BM25 + Naive + Parent + Compression + Multi-Query
- **Strength**: Leverages complementary strengths
- **Response Pattern**: Distinguishes between first film (positive) and later films (mixed)

### 7. **Semantic Retrieval** (Semantic Chunking)
- **Approach**: Semantic boundary-aware chunking
- **Documents**: 179 semantically coherent chunks
- **Strength**: Preserves meaning boundaries
- **Response Pattern**: Acknowledges series evolution and mixed later reception

---

## Analysis of Results

### Response Quality Patterns

| Method | Response Length | Temporal Awareness | Nuance Level | Series Coverage |
|--------|----------------|-------------------|--------------|-----------------|
| Naive | Medium | Low | Medium | First film focus |
| BM25 | Medium | High | High | Multi-film analysis |
| Contextual Compression | Long | Medium | High | Primarily first film |
| Multi-Query | Very Long | Low | Very High | Detailed first film |
| Parent Document | Medium | Medium | High | Balanced view |
| Ensemble | Long | High | Very High | Series-wide perspective |
| Semantic | Medium | High | High | Series evolution noted |

### Key Insights

1. **Document Loading Evolution**: This notebook showcases the **2024-2025 shift** where LangChain document loaders (like CSVLoader) no longer automatically chunk documents, allowing for direct vectorization of complete documents versus the historical practice of mandatory chunking.

2. **Temporal Awareness**: BM25 and Ensemble methods best captured the evolution of reception across the film series

3. **Detail vs. Brevity**: Multi-Query provided the most detailed analysis, while Naive was most concise

4. **Balanced Perspective**: Parent Document and Ensemble methods showed the most balanced positive/negative coverage

5. **Chunking Impact**: Semantic chunking (179 docs) vs traditional chunking (4,817 docs) shows dramatic efficiency gains

### Performance Characteristics

#### Document Count Analysis
- **Efficiency Winner**: Semantic chunking (179 docs) maintains quality with 96% fewer chunks
- **Context Preservation**: Parent document retrieval balances granular search with full context
- **Baseline Simplicity**: Direct document storage (100 docs) works well for focused queries

#### Search Strategy Effectiveness
- **Keyword Queries**: BM25 excels for specific term matching
- **Semantic Queries**: Vector similarity effective for concept-based searches  
- **Complex Queries**: Multi-query and ensemble methods handle nuanced questions best

---

## Best Practices and Recommendations

### When to Use Each Method

#### **Naive Retrieval**
- **Use For**: Simple questions, quick prototypes, baseline comparisons
- **Avoid When**: Need nuanced analysis or handling complex queries

#### **BM25 Retrieval**  
- **Use For**: Keyword-heavy queries, exact term matching, structured data
- **Avoid When**: Purely semantic/conceptual queries without clear keywords

#### **Contextual Compression**
- **Use For**: Large document sets with noise, precision-critical applications
- **Avoid When**: Budget constraints (requires additional API calls)

#### **Multi-Query Retrieval**
- **Use For**: Complex analytical questions, comprehensive coverage needs
- **Avoid When**: Simple queries, latency-sensitive applications

#### **Parent Document Retrieval**
- **Use For**: Need both precision and context, large documents
- **Avoid When**: Small documents or simple search requirements

#### **Ensemble Retrieval**
- **Use For**: Production systems, balanced performance across query types
- **Avoid When**: Simple use cases, computational resource constraints

#### **Semantic Retrieval**
- **Use For**: Concept-based queries, natural language understanding
- **Avoid When**: Keyword-specific searches, highly structured queries

### Implementation Strategy

1. **Start Simple**: Begin with naive retrieval for baseline
2. **Add Complexity Gradually**: Layer in BM25 for keyword enhancement
3. **Optimize for Use Case**: Choose ensemble for production, semantic for efficiency
4. **Monitor Performance**: Track response quality across different query types
5. **Consider Costs**: Balance API calls (compression/reranking) with performance gains

---

## Appendix: References and Citations

### Primary Sources - LangChain Documentation

1. **Ensemble Retriever**: 
   - How-to Guide: https://python.langchain.com/docs/how_to/ensemble_retriever/
   - API Reference: https://python.langchain.com/api_reference/langchain/retrievers/langchain.retrievers.ensemble.EnsembleRetriever.html

2. **Parent Document Retriever**: 
   - How-to Guide: https://python.langchain.com/docs/how_to/parent_document_retriever/
   - API Reference: https://python.langchain.com/api_reference/langchain/retrievers/langchain.retrievers.parent_document_retriever.ParentDocumentRetriever.html

3. **Contextual Compression**: 
   - How-to Guide: https://python.langchain.com/docs/how_to/contextual_compression/
   - API Reference: https://api.python.langchain.com/en/latest/retrievers/langchain.retrievers.contextual_compression.ContextualCompressionRetriever.html

4. **BM25 Retriever**:
   - Integration Guide: https://python.langchain.com/docs/integrations/retrievers/bm25/
   - API Reference: https://python.langchain.com/api_reference/community/retrievers/langchain_community.retrievers.bm25.BM25Retriever.html

### Technical Blog Posts

5. **LangChain Official Blog**:
   - "Improving Document Retrieval with Contextual Compression": https://blog.langchain.dev/improving-document-retrieval-with-contextual-compression/

6. **Research and Algorithm References**:
   - BM25 Algorithm (Wikipedia): https://en.wikipedia.org/wiki/Okapi_BM25
   - Reciprocal Rank Fusion: Used in ensemble retrieval for result combination

### Learning Resources

7. **Chunking Strategies**: 
   - Pinecone Learn: https://www.pinecone.io/learn/chunking-strategies/

8. **Advanced Tutorials**: 
   - Greg Kamradt's LangChain Tutorials: https://github.com/gkamradt/langchain-tutorials
   - Advanced Retrieval Notebook: https://github.com/gkamradt/langchain-tutorials/blob/main/data_generation/Advanced%20Retrieval%20With%20LangChain.ipynb

### Methodology References

- **Dataset**: John Wick movie reviews from AI-Maker-Space DataRepository
  - JW1: https://raw.githubusercontent.com/AI-Maker-Space/DataRepository/main/jw1.csv
  - JW2: https://raw.githubusercontent.com/AI-Maker-Space/DataRepository/main/jw2.csv  
  - JW3: https://raw.githubusercontent.com/AI-Maker-Space/DataRepository/main/jw3.csv
  - JW4: https://raw.githubusercontent.com/AI-Maker-Space/DataRepository/main/jw4.csv

- **Vector Database**: Qdrant Cloud with COSINE distance metric
- **Embeddings**: OpenAI text-embedding-3-small (1536 dimensions)
- **Reranking**: Cohere Rerank English v3.0
- **LLM**: GPT-4.1-mini for query generation and response synthesis

### Technical Implementation

- **Framework**: LangChain with langchain-qdrant integration
- **Environment**: Google Colab with UV package management
- **Configuration**: Cloud-based vector storage with gRPC protocol
- **Evaluation**: Qualitative analysis of response patterns and document retrieval counts

### Document Processing Evolution References

9. **LangChain Text Splitters Documentation**:
   - Current Guide: https://python.langchain.com/docs/concepts/text_splitters/
   - Legacy Documentation: https://python.langchain.com/v0.1/docs/modules/data_connection/document_transformers/

10. **CSV Loader Documentation**:
    - Current Integration: https://python.langchain.com/docs/integrations/document_loaders/csv/
    - Community Implementation: https://python.langchain.com/api_reference/community/document_loaders/langchain_community.document_loaders.csv_loader.CSVLoader.html

### Historical Context References

- **LangChain Architecture Evolution**: Clear separation between document loading and text splitting emerged in 2024, enabling comparison of chunked vs non-chunked approaches as demonstrated in this analysis
- **CSVLoader Behavior**: Modern CSVLoader creates one document per row without automatic chunking, representing the shift from integrated chunking to optional post-processing approaches

---

*This analysis demonstrates both the current state of retrieval methods and the historical evolution of LangChain's approach to document processing, highlighting how the separation of loading and chunking enables more nuanced comparisons of retrieval strategies.*