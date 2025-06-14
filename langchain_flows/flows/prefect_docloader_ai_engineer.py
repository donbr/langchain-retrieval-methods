import os
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from prefect import flow, task, get_run_logger
from prefect.artifacts import create_table_artifact, create_markdown_artifact, create_link_artifact
from prefect.events import emit_event
from langchain_community.document_loaders.pdf import PyPDFDirectoryLoader
from langchain_community.document_loaders import ArxivLoader, WebBaseLoader
from langchain_core.documents import Document
from huggingface_hub import login
from datasets import Dataset
import psycopg2
from psycopg2.extras import execute_batch, Json
from prefect.variables import Variable

import requests
import urllib3
import datetime
import uuid

# Set a default USER_AGENT if not already set
os.environ.setdefault("USER_AGENT", "langchain-retrieval-methods/1.0.0 (contact: dwbranson@gmail.com)")

# Load environment variables from .env file
load_dotenv()

# --- Validation Tasks ---

@task(
    name="validate-environment",
    description="Validates all required environment variables are set",
    retries=1,
    tags=["setup", "validation"]
)
def validate_environment() -> Dict[str, List[str]]:
    """
    Validates that all required environment variables are set.
    Returns a dictionary of environment categories and their values.
    """
    logger = get_run_logger()
    logger.info("Validating environment variables...")

    # Required variables for different operations
    required_vars = {
        "HuggingFace": ["HF_TOKEN"] if os.environ.get("HF_DOCLOADER_REPO") else [],
        "Postgres": ["POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "POSTGRES_TABLE"]
    }

    # Check for missing required variables
    missing_vars = {}
    for category, vars_list in required_vars.items():
        category_missing = [var for var in vars_list if var not in os.environ or not os.environ[var]]
        if category_missing:
            missing_vars[category] = category_missing
    
    # If any required variables are missing, log and raise error
    if missing_vars:
        error_msg = "Missing required environment variables:\n"
        for category, vars_list in missing_vars.items():
            error_msg += f"- {category}: {', '.join(vars_list)}\n"
        error_msg += "Please set these in your environment or .env file."
        
        logger.error(error_msg)
        create_markdown_artifact(
            key="environment-validation",
            markdown=f"# ❌ Environment Validation Failed\n\n{error_msg}",
            description="Environment validation status"
        )
        raise EnvironmentError(error_msg)
    
    logger.info("Environment validation successful")
    return {k: v for k, v in required_vars.items() if v}

@task(
    name="validate-input-parameters",
    description="Validates input parameters for the pipeline",
    tags=["setup", "validation"]
)
def validate_input_parameters(pdf_dir: str, arxiv_ids: List[str], html_urls: List[str], require_arxiv: bool = True) -> bool:
    """
    Validates input parameters for the pipeline.
    For the Azure HTML pipeline, arxiv_ids can be a dummy list and is not required.
    """
    logger = get_run_logger()
    logger.info("Validating input parameters...")
    
    errors = []
    
    # Validate PDF directory
    pdf_path = Path(pdf_dir)
    if not pdf_path.exists():
        logger.warning(f"PDF directory does not exist: {pdf_dir}. It will be created.")
        pdf_path.mkdir(parents=True, exist_ok=True)
        # Do not treat as error for Azure HTML pipeline
    
    # Validate arXiv IDs only if required
    if require_arxiv and not arxiv_ids:
        errors.append("ArXiv IDs list cannot be empty")
    
    # Validate HTML URLs
    if not html_urls:
        errors.append("HTML URLs list cannot be empty")
    
    for url in html_urls:
        if not url.startswith("http"):
            errors.append(f"Invalid URL format: {url}")
    
    # Create validation summary artifact
    create_table_artifact(
        key="input-parameters",
        table={
            "columns": ["Parameter", "Value", "Status"],
            "data": [
                ["PDF Directory", pdf_dir, "✅" if pdf_path.exists() else "⚠️ Created"],
                ["ArXiv IDs", str(arxiv_ids), "✅" if arxiv_ids or not require_arxiv else "❌"],
                ["HTML URLs", str(html_urls), "✅" if html_urls and all(url.startswith("http") for url in html_urls) else "❌"]
            ]
        },
        description="Validation status of input parameters"
    )
    
    if errors:
        error_msg = "Input validation failed:\n" + "\n".join(f"- {err}" for err in errors)
        logger.error(error_msg)
        create_markdown_artifact(
            key="input-validation",
            markdown=f"# ❌ Input Validation Failed\n\n{error_msg}",
            description="Input validation status"
        )
        raise ValueError(error_msg)
    
    logger.info("Input validation successful")
    return True

# --- Loader Tasks ---

@task(
    name="load-pdf-documents",
    description="Loads PDF documents from a directory using LangChain's PyPDFDirectoryLoader",
    retries=3,
    retry_delay_seconds=10,
    tags=["data", "pdf", "loading"]
)
def load_pdf_documents(pdf_dir: str) -> List[Document]:
    """
    Load PDF documents from a directory.
    
    Args:
        pdf_dir: Directory path containing PDF files
        
    Returns:
        List of Document objects from PDF files
    """
    logger = get_run_logger()
    
    try:
        # Ensure directory exists
        Path(pdf_dir).mkdir(parents=True, exist_ok=True)
        
        # Check if there are any PDF files
        pdf_files = list(Path(pdf_dir).glob("*.pdf"))
        if not pdf_files:
            logger.warning(f"No PDF files found in {pdf_dir}")
            create_markdown_artifact(
                key="pdf-loading-status",
                markdown=f"# ⚠️ No PDF Files Found\n\nNo PDF files were found in directory: `{pdf_dir}`",
                description="PDF Loading Warning"
            )
            return []
            
        # Load PDFs
        loader = PyPDFDirectoryLoader(pdf_dir, glob="*.pdf", silent_errors=True)
        docs = loader.load()
        
        # Enrich metadata
        for doc in docs:
            doc.metadata["loader_type"] = "pdf"
            doc.metadata["load_timestamp"] = datetime.datetime.now().isoformat()
        
        # Create artifact with loading statistics
        create_table_artifact(
            key="pdf-loading-stats",
            table={
                "columns": ["Metric", "Value"],
                "data": [
                    ["PDF Files Found", len(pdf_files)],
                    ["PDF Pages Loaded", len(docs)],
                    ["Source Directory", pdf_dir]
                ]
            },
            description="Statistics about PDF document loading"
        )
        
        # Emit event for monitoring
        emit_event(
            event="pdf-documents-loaded",
            resource={"prefect.resource.id": f"docloader-pipeline.pdf-docs.{pdf_dir}"},
            payload={
                "pdf_count": len(pdf_files),
                "page_count": len(docs),
                "source_dir": pdf_dir
            }
        )
        
        logger.info(f"Loaded {len(docs)} PDF pages from {len(pdf_files)} files in {pdf_dir}")
        return docs
        
    except Exception as e:
        error_msg = f"Error loading PDF documents: {str(e)}"
        logger.error(error_msg)
        create_markdown_artifact(
            key="pdf-loading-error",
            markdown=f"# ❌ PDF Loading Failed\n\n**Error:**\n```\n{str(e)}\n```\n\n**Source Directory:** {pdf_dir}",
            description="PDF loading error details"
        )
        raise

@task(
    name="load-arxiv-summaries",
    description="Loads document summaries from arXiv using IDs",
    retries=3,
    retry_delay_seconds=30,
    tags=["data", "arxiv", "loading"]
)
def load_arxiv_summaries(arxiv_ids: List[str]) -> List[Document]:
    """
    Load arXiv document summaries using IDs.
    
    Args:
        arxiv_ids: List of arXiv IDs to fetch
        
    Returns:
        List of Document objects containing arXiv summaries
    """
    logger = get_run_logger()
    all_docs = []
    failed_ids = []
    
    try:
        for arxiv_id in arxiv_ids:
            try:
                logger.debug(f"Loading arXiv data for ID: {arxiv_id}")
                loader = ArxivLoader(query=arxiv_id)
                docs = loader.get_summaries_as_docs()
                
                # Enrich metadata
                for doc in docs:
                    doc.metadata["loader_type"] = "arxiv"
                    doc.metadata["arxiv_id"] = arxiv_id
                    doc.metadata["load_timestamp"] = datetime.datetime.now().isoformat()
                    doc.metadata["doc_type"] = "summary"
                    
                all_docs.extend(docs)
                logger.debug(f"Loaded {len(docs)} documents for arXiv ID {arxiv_id}")
                
            except Exception as e:
                logger.error(f"Failed to load arXiv ID {arxiv_id}: {str(e)}")
                failed_ids.append((arxiv_id, str(e)))
                continue
        
        # Create artifact with loading statistics
        create_table_artifact(
            key="arxiv-loading-stats",
            table={
                "columns": ["Metric", "Value"],
                "data": [
                    ["ArXiv IDs Requested", len(arxiv_ids)],
                    ["ArXiv IDs Successfully Loaded", len(arxiv_ids) - len(failed_ids)],
                    ["ArXiv IDs Failed", len(failed_ids)],
                    ["Documents Loaded", len(all_docs)]
                ]
            },
            description="Statistics about arXiv document loading"
        )
        
        # If there were failures, create an artifact
        if failed_ids:
            failed_content = "\n".join([f"- {id}: {error}" for id, error in failed_ids])
            create_markdown_artifact(
                key="arxiv-loading-warnings",
                markdown=f"# ⚠️ Some arXiv IDs Failed to Load\n\n{failed_content}",
                description="ArXiv loading warnings"
            )
        
        # Emit event for monitoring
        emit_event(
            event="arxiv-documents-loaded",
            resource={"prefect.resource.id": "docloader-pipeline.arxiv-docs"},
            payload={
                "id_count": len(arxiv_ids),
                "success_count": len(arxiv_ids) - len(failed_ids),
                "failure_count": len(failed_ids),
                "doc_count": len(all_docs)
            }
        )
        
        logger.info(f"Loaded {len(all_docs)} arXiv metadata docs for {len(arxiv_ids)} IDs (with {len(failed_ids)} failures)")
        return all_docs
        
    except Exception as e:
        error_msg = f"Error loading arXiv documents: {str(e)}"
        logger.error(error_msg)
        create_markdown_artifact(
            key="arxiv-loading-error",
            markdown=f"# ❌ arXiv Loading Failed\n\n**Error:**\n```\n{str(e)}\n```\n\n**ArXiv IDs:** {arxiv_ids}",
            description="ArXiv loading error details"
        )
        raise

@task(
    name="load-webbase-html",
    description="Loads HTML content from web pages using WebBaseLoader",
    retries=3,
    retry_delay_seconds=30,
    tags=["data", "web", "loading"]
)
def load_webbase_html(urls: List[str]) -> List[Document]:
    """
    Load HTML content from web pages.
    
    Args:
        urls: List of URLs to fetch HTML content from
        
    Returns:
        List of Document objects with HTML content
    """
    logger = get_run_logger()
    all_docs = []
    failed_urls = []
    
    try:
        for url in urls:
            try:
                logger.debug(f"Loading HTML from URL: {url}")
                loader = WebBaseLoader(url)
                docs = loader.load()
                
                # Enrich metadata
                for doc in docs:
                    doc.metadata["loader_type"] = "webbase"
                    doc.metadata["source_url"] = url
                    doc.metadata["load_timestamp"] = datetime.datetime.now().isoformat()
                    doc.metadata["doc_type"] = "html"
                    
                all_docs.extend(docs)
                logger.debug(f"Loaded {len(docs)} documents from URL {url}")
                
            except Exception as e:
                logger.error(f"Failed to load URL {url}: {str(e)}")
                failed_urls.append((url, str(e)))
                continue
        
        # Create artifact with loading statistics
        create_table_artifact(
            key="web-loading-stats",
            table={
                "columns": ["Metric", "Value"],
                "data": [
                    ["URLs Requested", len(urls)],
                    ["URLs Successfully Loaded", len(urls) - len(failed_urls)],
                    ["URLs Failed", len(failed_urls)],
                    ["Documents Loaded", len(all_docs)]
                ]
            },
            description="Statistics about web document loading"
        )
        
        # If there were failures, create an artifact
        if failed_urls:
            failed_content = "\n".join([f"- {url}: {error}" for url, error in failed_urls])
            create_markdown_artifact(
                key="web-loading-warnings",
                markdown=f"# ⚠️ Some URLs Failed to Load\n\n{failed_content}",
                description="Web loading warnings"
            )
        
        # Emit event for monitoring
        emit_event(
            event="web-documents-loaded",
            resource={"prefect.resource.id": "docloader-pipeline.web-docs"},
            payload={
                "url_count": len(urls),
                "success_count": len(urls) - len(failed_urls),
                "failure_count": len(failed_urls),
                "doc_count": len(all_docs)
            }
        )
        
        logger.info(f"Loaded {len(all_docs)} HTML docs from {len(urls)} URLs (with {len(failed_urls)} failures)")
        return all_docs
        
    except Exception as e:
        error_msg = f"Error loading web documents: {str(e)}"
        logger.error(error_msg)
        create_markdown_artifact(
            key="web-loading-error",
            markdown=f"# ❌ Web Loading Failed\n\n**Error:**\n```\n{str(e)}\n```\n\n**URLs:** {urls}",
            description="Web loading error details"
        )
        raise

@task(
    name="save-docs-json",
    description="Saves documents to JSON file with metadata",
    tags=["data", "output", "json"]
)
def save_docs_json(docs: List[Document], filename: str, output_dir: str = "output") -> str:
    """
    Save documents to a JSON file.
    
    Args:
        docs: List of documents to save
        filename: Output filename for the JSON
        output_dir: Directory to save the file in
        
    Returns:
        Path to the saved JSON file
    """
    logger = get_run_logger()
    
    try:
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)
        out_path = output_dir_path / filename
        
        serializable_docs = [
            {"page_content": doc.page_content, "metadata": doc.metadata}
            for doc in docs
        ]
        
        def json_default(obj):
            if isinstance(obj, (datetime.date, datetime.datetime)):
                return obj.isoformat()
            raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")
            
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(serializable_docs, f, ensure_ascii=False, indent=2, default=json_default)
            
        logger.info(f"Saved {len(docs)} documents to {out_path}")
        
        # Sanitize key: remove extension, replace underscores with dashes
        sanitized_key = filename.rsplit('.', 1)[0].replace('_', '-')
        
        # Create artifacts to make the file easily accessible
        create_link_artifact(
            key=f"{sanitized_key}-json",
            link=f"file://{os.path.abspath(out_path)}",
            link_text=f"Saved {filename}",
            description=f"Link to the saved {filename} in JSON format"
        )
        
        # Create a table showing metadata fields present in the documents
        if docs:
            all_metadata_fields = set()
            for doc in docs:
                all_metadata_fields.update(doc.metadata.keys())
                
            create_table_artifact(
                key=f"{sanitized_key}-metadata-fields",
                table={
                    "columns": ["Metadata Field", "Present In"],
                    "data": [
                        [field, f"{sum(1 for doc in docs if field in doc.metadata)}/{len(docs)} docs"]
                        for field in sorted(all_metadata_fields)
                    ]
                },
                description=f"Metadata fields present in {filename} documents"
            )
        
        return str(out_path)
        
    except Exception as e:
        error_msg = f"Error saving documents to JSON: {str(e)}"
        logger.error(error_msg)
        create_markdown_artifact(
            key=f"{sanitized_key}-save-error",
            markdown=f"# ❌ JSON Save Failed\n\n**Error:**\n```\n{str(e)}\n```\n\n**Target:** {output_dir}/{filename}",
            description="JSON save error details"
        )
        raise

# --- Save and Push to HuggingFace ---

@task(
    name="prepare-hf-dataset",
    description="Prepares documents for HuggingFace dataset format",
    tags=["huggingface", "processing"]
)
def prepare_hf_dataset(all_docs: List[Document]) -> List[Dict[str, str]]:
    """
    Prepare documents for HuggingFace dataset format.
    
    Args:
        all_docs: List of all documents to prepare
        
    Returns:
        List of records ready for HF dataset creation
    """
    logger = get_run_logger()
    
    try:
        def prune_and_serialize(meta: dict) -> str:
            clean = {}
            for k, v in meta.items():
                # drop empty
                if v in (None, "", [], {}):
                    continue
                # normalize dates
                if isinstance(v, (datetime.date, datetime.datetime)):
                    v = v.isoformat()
                clean[k] = v
            return json.dumps(clean, ensure_ascii=False)

        records = []
        for doc in all_docs:
            # support both dicts and Document-like objects
            pc   = doc.get("page_content") if isinstance(doc, dict) else getattr(doc, "page_content", "")
            meta = doc.get("metadata", {})   if isinstance(doc, dict) else getattr(doc, "metadata", {})
            records.append({
                "page_content": pc,
                "metadata_json": prune_and_serialize(meta)
            })
            
        logger.info(f"Prepared {len(records)} records for HuggingFace dataset/Postgres upload")
        return records
        
    except Exception as e:
        error_msg = f"Error preparing HuggingFace dataset: {str(e)}"
        logger.error(error_msg)
        create_markdown_artifact(
            key="hf-preparation-error",
            markdown=f"# ❌ HuggingFace Dataset Preparation Failed\n\n**Error:**\n```\n{str(e)}\n```",
            description="HuggingFace preparation error"
        )
        raise

@task(
    name="push-to-huggingface",
    description="Pushes prepared dataset to HuggingFace Hub",
    retries=2,
    retry_delay_seconds=60,
    tags=["huggingface", "publish"]
)
def push_to_huggingface(records: List[Dict[str, str]], repo_name: str) -> str:
    """
    Push prepared dataset records to HuggingFace Hub.
    
    Args:
        records: Prepared dataset records
        repo_name: HuggingFace repository name
        
    Returns:
        URL of the published dataset
    """
    logger = get_run_logger()
    
    try:
        token = os.environ.get("HF_TOKEN")
        if not token:
            raise RuntimeError("HF_TOKEN not set in environment.")
            
        login(token=token, add_to_git_credential=False)
        ds = Dataset.from_list(records)
        ds.push_to_hub(repo_name)

        url = f"https://huggingface.co/datasets/{repo_name}"
        
        # Create success artifacts
        create_markdown_artifact(
            key="hf-push-success",
            markdown=f"# ✅ Dataset Published\n\n**Repository:** [{repo_name}]({url})\n\n**Record Count:** {len(records)}",
            description="HuggingFace publication success",
        )
        
        # Emit event for monitoring
        emit_event(
            event="dataset-published",
            resource={"prefect.resource.id": f"docloader-pipeline.dataset.{repo_name}"},
            payload={
                "repo_name": repo_name,
                "record_count": len(records),
                "url": url
            }
        )
        
        logger.info(f"Successfully pushed dataset with {len(records)} records to {url}")
        return url
        
    except Exception as e:
        error_msg = f"Error pushing to HuggingFace: {str(e)}"
        logger.error(error_msg)
        create_markdown_artifact(
            key="hf-push-error",
            markdown=f"# ❌ HuggingFace Push Failed\n\n**Error:**\n```\n{str(e)}\n```\n\n**Repository:** {repo_name}\n**Record Count:** {len(records)}",
            description="HuggingFace push error"
        )
        raise

# --- Postgres Connection Helper ---
def get_postgres_connection():
    """
    Get a Postgres connection using SUPABASE_DB_URL only.
    """
    import psycopg2
    db_url = os.environ["SUPABASE_DB_URL"]
    return psycopg2.connect(db_url)

@task(
    name="upload-to-postgres",
    description="Uploads processed documents to a Postgres database using the new schema.",
    retries=2,
    retry_delay_seconds=30,
    tags=["postgres", "database", "output"]
)
def upload_to_postgres(records: List[Dict[str, str]]):
    """
    Uploads records to the azure_arch_cert_documents table with the new schema:
      - id (uuid primary key)
      - content (text)
      - metadata (jsonb)
      - embedding (vector(1536)), set to NULL for now
    """
    logger = get_run_logger()
    try:
        conn = get_postgres_connection()
        table = "azure_arch_cert_documents"
        with conn:
            with conn.cursor() as cur:
                # Create table if not exists with the new schema
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {table} (
                        id uuid PRIMARY KEY,
                        content text,
                        metadata jsonb,
                        embedding vector(1536)
                    );
                """)
                # Insert records (embedding is set to NULL for now)
                data = [
                    (
                        str(uuid.uuid4()),
                        r["page_content"],
                        Json(json.loads(r["metadata_json"])) if isinstance(r["metadata_json"], str) else Json(r["metadata_json"]),
                        None
                    )
                    for r in records
                ]
                execute_batch(
                    cur,
                    f"INSERT INTO {table} (id, content, metadata, embedding) VALUES (%s, %s, %s, %s)",
                    data
                )
        logger.info(f"Uploaded {len(records)} records to Postgres table '{table}' with new schema")
        return f"Uploaded {len(records)} records to Postgres table '{table}' with new schema"
    except Exception as e:
        logger.error(f"Error uploading to Postgres: {str(e)}")
        raise

# --- Main Flow ---

@flow(
    name="Azure AI Engineer Renewal Document Pipeline",
    description="Downloads and processes Azure AI Engineer renewal module HTML files.",
    log_prints=True,
    version=os.environ.get("PIPELINE_VERSION", "1.0.0")
)
def azure_ai_engineer_docloader_pipeline(
    HTML_URLS: List[str] = [],
    HTML_DOWNLOAD_DIR: str = "azure_ai_engineer_html",
    HF_DOCLOADER_REPO: str = os.environ.get("HF_DOCLOADER_REPO", ""),
):
    """
    Pipeline to download and process Azure AI Engineer renewal module HTML files.
    1. Download all HTML files (checkpoint)
    2. Process downloaded files by reading as text and wrapping in LangChain Document objects (established, dependency-free pattern)
    """
    logger = get_run_logger()
    logger.info("Starting Azure AI Engineer Renewal Document Pipeline")

    # If HTML_URLS is empty, import from azure_ai_engineer_renewal.py
    if not HTML_URLS:
        from langchain_flows.flows.azure_ai_engineer_renewal import (
            SPEECH_ENABLED_APPS_URLS,
            TRANSLATE_SPEECH_URLS,
            CREATE_AZURE_AI_CUSTOM_SKILL_URLS,
            BUILD_LANGUAGE_UNDERSTANDING_MODEL_URLS,
            INVESTIGATE_CONTAINER_URLS,
            ANALYZE_TEXT_URLS,
            DEVELOP_OPENAI_URLS,
            CREATE_QA_SOLUTION_URLS,
            USE_OWN_DATA_URLS,
            FORM_RECOGNIZER_URLS,
            ANALYZE_IMAGES_URLS,
        )
        HTML_URLS = (
            SPEECH_ENABLED_APPS_URLS
            + TRANSLATE_SPEECH_URLS
            + CREATE_AZURE_AI_CUSTOM_SKILL_URLS
            + BUILD_LANGUAGE_UNDERSTANDING_MODEL_URLS
            + INVESTIGATE_CONTAINER_URLS
            + ANALYZE_TEXT_URLS
            + DEVELOP_OPENAI_URLS
            + CREATE_QA_SOLUTION_URLS
            + USE_OWN_DATA_URLS
            + FORM_RECOGNIZER_URLS
            + ANALYZE_IMAGES_URLS
        )

    # Create artifact with pipeline configuration
    create_table_artifact(
        key="azure-ai-engineer-pipeline-configuration",
        table={
            "columns": ["Parameter", "Value"],
            "data": [
                ["HTML URLs", str(HTML_URLS)],
                ["HTML Download Directory", HTML_DOWNLOAD_DIR],
                ["HuggingFace Repository", HF_DOCLOADER_REPO or "Not specified"]
            ]
        },
        description="Azure AI Engineer pipeline configuration parameters"
    )

    validate_environment()
    validate_input_parameters(HTML_DOWNLOAD_DIR, ["dummy"], HTML_URLS, require_arxiv=False)

    # 1. Load HTML documents using WebBaseLoader (established pattern)
    webbase_future = load_webbase_html.submit(HTML_URLS)
    docs = webbase_future.result()

    # --- Debug: limit number of docs for debugging ---
    max_docs = None
    try:
        max_docs = Variable.get("max_docs_debug", default=None)
    except Exception:
        max_docs = os.environ.get("MAX_DOCS_DEBUG", None)
    if max_docs is not None:
        try:
            max_docs_int = int(max_docs)
            logger.info(f"⚠️  Limiting documents to first {max_docs_int} for debugging (max_docs_debug)")
            docs = docs[:max_docs_int]
        except Exception as e:
            logger.warning(f"Could not apply max_docs_debug: {e}")
    logger.info(f"Number of documents after debug limiting: {len(docs)}")

    html_file = save_docs_json(docs, "azure_ai_engineer_html_docs.json")

    # Create summary statistics artifact
    create_table_artifact(
        key="azure-ai-engineer-document-summary",
        table={
            "columns": ["Source", "Document Count", "Output File"],
            "data": [
                ["Azure AI Engineer HTML", len(docs), html_file],
            ]
        },
        description="Summary of Azure AI Engineer HTML documents loaded"
    )

    # Push to HuggingFace if repository is specified
    if HF_DOCLOADER_REPO:
        logger.info(f"Preparing to push {len(docs)} documents to HuggingFace repo: {HF_DOCLOADER_REPO}")
        records = prepare_hf_dataset(docs)
        hf_url = push_to_huggingface(records, HF_DOCLOADER_REPO)
    else:
        logger.info("No HF_DOCLOADER_REPO specified; skipping push.")

    # Upload to Postgres
    logger.info(f"Preparing to upload {len(docs)} documents to Postgres")
    records = prepare_hf_dataset(docs)
    upload_to_postgres(records)

    # Final success artifact
    create_markdown_artifact(
        key="azure-ai-engineer-pipeline-summary",
        markdown=f"""# Azure AI Engineer Pipeline Execution Summary\n\n## Success! ✅\n\nThe Azure AI Engineer Renewal Document Pipeline completed successfully.\n\n## Statistics\n- HTML Documents: {len(docs)}\n\n## Outputs\n- HTML JSON: `{html_file}`\n{f'- Published to: [{HF_DOCLOADER_REPO}](https://huggingface.co/datasets/{HF_DOCLOADER_REPO})' if HF_DOCLOADER_REPO else ''}\n""",
        description="Azure AI Engineer pipeline execution summary"
    )

    logger.info("Azure AI Engineer Pipeline complete.")
    return {
        "html_count": len(docs),
        "output_file": html_file,
        "hf_repo": HF_DOCLOADER_REPO if HF_DOCLOADER_REPO else None
    }

if __name__ == "__main__":
    azure_ai_engineer_docloader_pipeline()
