from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from datetime import datetime
import asyncio
from io import BytesIO
import xml.etree.ElementTree as ET
import gzip
import re
from pypdf import PdfReader
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import time

from app.services.rag_service import rag_service
from app.core.security import get_current_user_id
from app.core.database import get_db, DocumentDB, TenantUsageDB
from app.core.logging import logger
from app.core.usage_limits import check_document_quota, remaining_document_slots
from app.core.config import get_settings
from app.core.url_security import is_safe_outbound_url
from app.core.telemetry import get_tracer

tracer = get_tracer("ingest_service")

settings = get_settings()

router = APIRouter()

_NOISE_PATTERNS = [
    r"\brequest a call back\b",
    r"\bview more\b",
    r"\bread more\b",
    r"\bquick view\b",
    r"\bfilter\b",
    r"\bsort by\b",
    r"\bmenu\b",
    r"\blogin\b",
    r"\bsign ?in\b",
    r"\bsign ?up\b",
    r"\bsubscribe\b",
    r"\bprivacy policy\b",
    r"\bterms (and|&) conditions\b",
]
_NOISE_LINE_RE = re.compile("|".join(_NOISE_PATTERNS), re.IGNORECASE)

def _canonical_host(host: str) -> str:
    host = (host or "").strip().lower()
    if host.startswith("www."):
        return host[4:]
    return host


def _same_domain(a: str, b: str) -> bool:
    # Use strict domain matching - require exact match (including www prefix)
    # This prevents mixing https://example.com with https://www.example.com
    a_lower = (a or "").strip().lower()
    b_lower = (b or "").strip().lower()
    return a_lower == b_lower

def _host_variants(host: str) -> List[str]:
    host = (host or "").strip().lower()
    if not host:
        return []
    if host.startswith("www."):
        return [host, host[4:]]
    return [host, f"www.{host}"]


def _detect_correct_domain_variant(base_url: str, timeout: int = 5) -> Optional[str]:
    """
    Detect the correct domain variant (www vs non-www) by testing both variants.
    If the provided variant fails, try the alternate and return the working one.
    
    Args:
        base_url: The base URL provided by the user
        timeout: Request timeout in seconds
        
    Returns:
        The corrected base_url if alternate works, None if original works, or original if both fail
    """
    try:
        parsed = urlparse(base_url)
        original_host = parsed.netloc.lower()
        
        # Get the alternate variant
        variants = _host_variants(original_host)
        if len(variants) < 2:
            return None  # No variant available
        
        alternate_host = variants[1]
        if alternate_host == original_host:
            return None  # No alternate variant
        
        # Test original URL
        try:
            response = requests.head(base_url, timeout=timeout, allow_redirects=True)
            if response.status_code < 400:
                return None  # Original works
        except Exception:
            pass  # Original failed, test alternate
        
        # Test alternate URL
        alternate_url = base_url.replace(original_host, alternate_host, 1)
        try:
            response = requests.head(alternate_url, timeout=timeout, allow_redirects=True)
            if response.status_code < 400:
                logger.info("domain_variant_corrected", extra={
                    "original_domain": original_host,
                    "corrected_domain": alternate_host,
                    "original_url": base_url,
                    "corrected_url": alternate_url
                })
                return alternate_url  # Alternate works better
        except Exception:
            pass  # Alternate also failed
        
        return None  # Both failed or original is correct
        
    except Exception as e:
        logger.debug("domain_variant_detection_error", extra={"error": str(e)})
        return None


def _increment_usage(db: Session, tenant_id: str, field: str, amount: int = 1):
    usage = db.query(TenantUsageDB).filter(TenantUsageDB.tenant_id == tenant_id).first()
    if not usage:
        usage = TenantUsageDB(tenant_id=tenant_id)
        db.add(usage)
    
    current_val = getattr(usage, field) or 0
    setattr(usage, field, current_val + amount)
    db.commit()


def _decrement_usage(db: Session, tenant_id: str, field: str, amount: int = 1):
    usage = db.query(TenantUsageDB).filter(TenantUsageDB.tenant_id == tenant_id).first()
    if not usage:
        return

    current_val = getattr(usage, field) or 0
    setattr(usage, field, max(0, current_val - amount))
    db.commit()

class WebScrapeRequest(BaseModel):
    url: str
    max_pages: Optional[int] = 3000
    use_sitemaps: Optional[bool] = True
    index_sections: Optional[bool] = True


def _extract_upload_text(filename: str, content: bytes) -> str:
    text = ""
    if filename.lower().endswith('.pdf'):
        try:
            pdf_reader = PdfReader(BytesIO(content))
            for page in pdf_reader.pages:
                extract = page.extract_text()
                if extract:
                    text += extract + "\n"
            return text
        except Exception as e:
            raise ValueError(f"Error parsing PDF: {str(e)}")
    if filename.lower().endswith(('.txt', '.md')):
        try:
            return content.decode('utf-8')
        except Exception as e:
            raise ValueError(f"Error reading text file: {str(e)}")
    raise HTTPException(status_code=400, detail="Unsupported file type. Only .pdf, .txt, .md supported.")

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    tenant_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    try:
        check_document_quota(db, tenant_id, amount=1)
        content = await file.read()
        filename = file.filename
        if len(content) > settings.MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Uploaded file exceeds size limit")
        try:
            text = await asyncio.to_thread(_extract_upload_text, filename, content)
        except HTTPException:
            raise
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error parsing upload: {str(e)}")
             
        if not text.strip():
            raise HTTPException(status_code=400, detail="Empty file content")

        # Reuse Logic: Create DB Record
        db_doc = DocumentDB(
            title=filename,
            source="upload",
            content_snippet=text[:200].replace('\n', ' '),
            tenant_id=tenant_id
        )
        db.add(db_doc)
        db.flush()
        
        # Index
        metadata = {"source": filename, "doc_id": db_doc.id, "title": filename}
        await asyncio.to_thread(rag_service.ingest_text, text, metadata, collection_name=tenant_id)
        
        _increment_usage(db, tenant_id, "documents_indexed")
        
        db.commit()
        db.refresh(db_doc)

        logger.info("document_uploaded", extra={
            "doc_id": db_doc.id, "file_name": filename,
            "tenant_id": tenant_id, "text_length": len(text)
        })
        
        return {"status": "success", "db_id": db_doc.id, "filename": filename}

    except HTTPException as he:
        db.rollback()
        raise he
    except Exception as e:
        logger.error("upload_failed", extra={
            "tenant_id": tenant_id, "file_name": file.filename, "error": str(e)
        })
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

class IngestRequest(BaseModel):
    text: str
    metadata: Dict = {}

class DocumentResponse(BaseModel):
    id: int
    title: str
    source: str
    created_at: datetime
    content_snippet: str


class AuditTestRequest(BaseModel):
    bot_id: int
    question: str
    expected_keyword: Optional[str] = ""


class AuditTestResponse(BaseModel):
    answer: str
    passed: Optional[bool] = None
    response_ms: int
    sources: List[Dict] = []

@router.post("/")
async def ingest(
    request: IngestRequest, 
    tenant_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    try:
        check_document_quota(db, tenant_id, amount=1)
        # 1. Save metadata to SQL DB first to get the ID
        title = request.metadata.get("title", "Untitled")
        source = request.metadata.get("source", "unknown")
        snippet = request.text[:100] + "..." if len(request.text) > 100 else request.text
        
        db_doc = DocumentDB(
            title=title,
            source=source,
            content_snippet=snippet,
            tenant_id=tenant_id
        )
        db.add(db_doc)
        db.flush() # Flush to populate db_doc.id
        
        # 2. Ingest into the vector store with doc_id in metadata
        request.metadata["doc_id"] = db_doc.id
        result = await asyncio.to_thread(rag_service.ingest_text, request.text, request.metadata, collection_name=tenant_id)
        
        _increment_usage(db, tenant_id, "documents_indexed")
        
        db.commit()
        db.refresh(db_doc)

        logger.info("document_ingested", extra={
            "doc_id": db_doc.id, "title": title, "tenant_id": tenant_id,
            "text_length": len(request.text), "chunks": result.get("chunks_added", 0)
        })
        
        return {"status": "success", "db_id": db_doc.id, "vector_status": result}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        logger.error("ingest_failed", extra={"tenant_id": tenant_id, "error": str(e)})
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{doc_id}")
async def delete_document(
    doc_id: int,
    tenant_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    try:
        # 1. Get doc from DB
        db_doc = db.query(DocumentDB).filter(DocumentDB.id == doc_id, DocumentDB.tenant_id == tenant_id).first()
        if not db_doc:
            raise HTTPException(status_code=404, detail="Document not found")
            
        # 2. Delete from Vector DB
        rag_service.delete_document(doc_id, collection_name=tenant_id)
        
        # 3. Delete from SQL DB
        db.delete(db_doc)
        db.commit()
        _decrement_usage(db, tenant_id, "documents_indexed")
        
        logger.info("document_deleted", extra={
            "doc_id": doc_id, "tenant_id": tenant_id, "title": db_doc.title
        })
        
        return {"status": "success", "id": doc_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("document_delete_failed", extra={"doc_id": doc_id, "error": str(e)})
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=List[DocumentResponse])
async def list_documents(
    tenant_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    try:
        docs = db.query(DocumentDB).filter(DocumentDB.tenant_id == tenant_id).order_by(DocumentDB.created_at.desc()).all()
        deduped_docs = []
        seen_web_sources = set()
        for doc in docs:
            source = (doc.source or "").strip().lower()
            if source.startswith("http://") or source.startswith("https://"):
                normalized_source = _normalize_url(doc.source)
                if normalized_source in seen_web_sources:
                    continue
                seen_web_sources.add(normalized_source)
            deduped_docs.append(doc)
        return deduped_docs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audit/summary")
async def crawl_audit_summary(
    tenant_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    try:
        docs = db.query(DocumentDB).filter(
            DocumentDB.tenant_id == tenant_id
        ).order_by(DocumentDB.created_at.desc()).all()

        web_docs = [
            d for d in docs
            if (d.source or "").startswith("http://") or (d.source or "").startswith("https://")
        ]
        file_docs = len(docs) - len(web_docs)

        unique_sources = set()
        duplicate_count = 0
        domain_counts = {}

        for doc in web_docs:
            normalized_source = _normalize_url(doc.source)
            if normalized_source in unique_sources:
                duplicate_count += 1
            else:
                unique_sources.add(normalized_source)
                domain = urlparse(normalized_source).netloc.lower() or "unknown"
                domain_counts[domain] = domain_counts.get(domain, 0) + 1

        top_domains = [
            {"domain": domain, "pages": pages}
            for domain, pages in sorted(domain_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        ]

        last_crawl_at = max((d.created_at for d in web_docs), default=None)
        last_upload_at = max((d.created_at for d in docs if d not in web_docs), default=None)

        return {
            "total_documents": len(docs),
            "web_documents": len(web_docs),
            "file_documents": file_docs,
            "unique_web_sources": len(unique_sources),
            "duplicate_web_documents": duplicate_count,
            "last_crawl_at": last_crawl_at,
            "last_upload_at": last_upload_at,
            "top_domains": top_domains,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/audit/test-runner", response_model=AuditTestResponse)
async def audit_test_runner(
    request: AuditTestRequest,
    tenant_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from app.models.bot import Bot

    bot = db.query(Bot).filter(Bot.id == request.bot_id, Bot.tenant_id == tenant_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    question = (request.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")

    start = datetime.utcnow()
    result = rag_service.answer_from_knowledge_ledger(
        question=question,
        collection_name=tenant_id,
        k=5,
        bot_instructions=(bot.prompt_template or "").strip(),
        bot_name=bot.name,
    )
    elapsed_ms = int((datetime.utcnow() - start).total_seconds() * 1000)
    answer = (result.get("answer") or "").strip()
    expected_keyword = (request.expected_keyword or "").strip()
    passed = None
    if expected_keyword:
        passed = expected_keyword.lower() in answer.lower()

    return {
        "answer": answer,
        "passed": passed,
        "response_ms": max(0, elapsed_ms),
        "sources": result.get("sources") or [],
    }

def _get_internal_links(soup, base_url, domain):
    from urllib.parse import urljoin
    links = []
    domain_mismatches = 0

    def maybe_add(raw_url: str):
        nonlocal domain_mismatches
        full_url = urljoin(base_url, raw_url)
        parsed_full = urlparse(full_url)
        if not _same_domain(parsed_full.netloc, domain):
            domain_mismatches += 1
            return
        if parsed_full.fragment:
            return
        clean_url = _normalize_url(f"{parsed_full.scheme}://{parsed_full.netloc}{parsed_full.path}")
        if _should_skip_url(clean_url):
            return
        links.append(clean_url)

    for a in soup.find_all('a', href=True):
        maybe_add(a['href'])

    # Extract URLs from script content (JSON-LD, hydration blobs, route manifests).
    url_pattern = re.compile(r"https?://[^\"'\\s<>]+|/[^\"'\\s<>]+")
    for script in soup.find_all("script"):
        script_text = script.string or script.get_text() or ""
        if not script_text:
            continue
        for match in url_pattern.findall(script_text):
            if match.startswith("//"):
                continue
            maybe_add(match)

    if domain_mismatches > 0:
        logger.debug("domain_mismatches_filtered", extra={
            "base_url": base_url,
            "target_domain": domain,
            "mismatches_skipped": domain_mismatches
        })

    return links


def _normalize_url(url: str) -> str:
    from urllib.parse import urlparse
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path or ""

    # Canonicalize common default home documents.
    lower_path = path.lower()
    if lower_path.endswith("/index.html"):
        path = path[:-11]
    elif lower_path.endswith("/index.htm"):
        path = path[:-10]

    if path != "/":
        path = path.rstrip("/")
    if path == "/":
        path = ""
    return f"{scheme}://{netloc}{path}"


def _should_skip_url(url: str) -> bool:
    parsed = urlparse(url)
    path = (parsed.path or "").lower()

    # Skip static assets and non-content endpoints.
    static_ext = (
        ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico",
        ".css", ".js", ".map", ".woff", ".woff2", ".ttf", ".eot",
        ".xml", ".json", ".pdf", ".zip", ".mp4", ".mp3"
    )
    if path.endswith(static_ext):
        return True
    if path.startswith(("/cdn-cgi/", "/wp-admin", "/admin", "/cart", "/checkout", "/account")):
        return True
    return False


def _build_existing_web_doc_map(db: Session, tenant_id: str):
    docs = db.query(DocumentDB).filter(DocumentDB.tenant_id == tenant_id).all()
    existing = {}
    for doc in docs:
        source = (doc.source or "").strip().lower()
        if not (source.startswith("http://") or source.startswith("https://")):
            continue
        existing[_normalize_url(doc.source)] = doc
    return existing


def _extract_sitemaps_from_robots(base_url: str, headers: Dict[str, str]) -> List[str]:
    with tracer.start_as_current_span("extract_sitemaps_from_robots") as span:
        span.set_attribute("base_url", base_url)
        try:
            parsed = urlparse(base_url)
            robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
            span.set_attribute("robots_url", robots_url)
            
            logger.info("robots_fetch_start", extra={"robots_url": robots_url})
            response = requests.get(robots_url, headers=headers, timeout=8)
            
            logger.info("robots_fetch_response", extra={
                "robots_url": robots_url,
                "status_code": response.status_code,
                "response_size": len(response.text)
            })
            span.set_attribute("robots_status_code", response.status_code)
            
            if response.status_code != 200:
                logger.warning("robots_not_found", extra={"robots_url": robots_url, "status": response.status_code})
                return []
            
            sitemaps = []
            for line in response.text.splitlines():
                if line.lower().startswith("sitemap:"):
                    sitemap_url = line.split(":", 1)[1].strip()
                    if sitemap_url:
                        sitemaps.append(sitemap_url)
                        logger.debug("sitemap_found_in_robots", extra={"sitemap_url": sitemap_url})
            
            logger.info("robots_parse_complete", extra={"sitemaps_found": len(sitemaps)})
            span.set_attribute("sitemaps_found", len(sitemaps))
            return sitemaps
        except requests.exceptions.Timeout as e:
            logger.error("robots_timeout", extra={"base_url": base_url, "error": str(e)})
            span.set_attribute("error_type", "timeout")
            return []
        except requests.exceptions.RequestException as e:
            logger.error("robots_request_failed", extra={"base_url": base_url, "error": str(e)})
            span.set_attribute("error_type", "request_exception")
            return []
        except Exception as e:
            logger.error("robots_extraction_failed", extra={"base_url": base_url, "error": str(e)})
            span.set_attribute("error_type", "generic_exception")
            return []


def _fetch_sitemap_urls(base_url: str, headers: Dict[str, str], domain: str, max_urls: int = 30000) -> List[str]:
    with tracer.start_as_current_span("fetch_sitemap_urls") as span:
        span.set_attribute("base_url", base_url)
        span.set_attribute("domain", domain)
        span.set_attribute("max_urls", max_urls)
        
        parsed = urlparse(base_url)
        seed_sitemaps = set()
        for host in _host_variants(parsed.netloc):
            seed_sitemaps.update({
                f"{parsed.scheme}://{host}/sitemap.xml",
                f"{parsed.scheme}://{host}/sitemap_index.xml",
                f"{parsed.scheme}://{host}/sitemap.xml.gz",
                f"{parsed.scheme}://{host}/sitemap_index.xml.gz",
                f"{parsed.scheme}://{host}/product-sitemap.xml",
                f"{parsed.scheme}://{host}/product-sitemap.xml.gz",
                f"{parsed.scheme}://{host}/page-sitemap.xml",
                f"{parsed.scheme}://{host}/category-sitemap.xml",
            })
        
        for sm in _extract_sitemaps_from_robots(base_url, headers):
            seed_sitemaps.add(sm)

        logger.info("sitemap_discovery_start", extra={
            "base_url": base_url,
            "domain": domain,
            "seed_sitemaps": len(seed_sitemaps),
            "standard_paths": 8
        })
        span.set_attribute("seed_sitemaps_count", len(seed_sitemaps))

        sitemap_queue = list(seed_sitemaps)
        visited_sitemaps = set()
        discovered_urls = []
        seen_urls = set()
        fetch_errors = []
        domain_mismatch_urls = 0

        while sitemap_queue and len(discovered_urls) < max_urls:
            sitemap_url = sitemap_queue.pop(0)
            if sitemap_url in visited_sitemaps:
                continue
            visited_sitemaps.add(sitemap_url)

            try:
                logger.debug("fetching_sitemap", extra={"sitemap_url": sitemap_url})
                fetch_start = time.time()
                response = requests.get(sitemap_url, headers=headers, timeout=12)
                fetch_elapsed = time.time() - fetch_start
                
                logger.debug("sitemap_fetch_complete", extra={
                    "sitemap_url": sitemap_url,
                    "status_code": response.status_code,
                    "response_size": len(response.content),
                    "fetch_time_seconds": round(fetch_elapsed, 2)
                })
                
                if response.status_code != 200:
                    logger.warning("sitemap_fetch_failed", extra={
                        "sitemap_url": sitemap_url,
                        "status_code": response.status_code
                    })
                    fetch_errors.append({"url": sitemap_url, "status": response.status_code})
                    continue

                content = response.content
                if sitemap_url.endswith(".gz"):
                    try:
                        logger.debug("decompressing_gzip_sitemap", extra={"sitemap_url": sitemap_url})
                        content = gzip.decompress(content)
                        logger.debug("gzip_decompressed", extra={
                            "sitemap_url": sitemap_url,
                            "decompressed_size": len(content)
                        })
                    except Exception as e:
                        logger.error("gzip_decompression_failed", extra={
                            "sitemap_url": sitemap_url,
                            "error": str(e)
                        })
                        continue

                try:
                    root = ET.fromstring(content)
                    root_tag = root.tag.lower()
                    is_index = root_tag.endswith("sitemapindex")
                    
                    logger.debug("sitemap_parsed", extra={
                        "sitemap_url": sitemap_url,
                        "is_index": is_index,
                        "root_tag": root_tag
                    })

                    for loc in root.findall(".//{*}loc"):
                        loc_url = (loc.text or "").strip()
                        if not loc_url:
                            continue
                        parsed_loc = urlparse(loc_url)
                        if not _same_domain(parsed_loc.netloc, domain):
                            domain_mismatch_urls += 1
                            logger.debug("url_domain_mismatch", extra={
                                "url": loc_url,
                                "expected_domain": domain,
                                "actual_domain": parsed_loc.netloc
                            })
                            continue

                        normalized = _normalize_url(loc_url)
                        if is_index:
                            if normalized not in visited_sitemaps:
                                logger.debug("adding_child_sitemap", extra={"sitemap_url": normalized})
                                sitemap_queue.append(normalized)
                        else:
                            if normalized not in seen_urls:
                                seen_urls.add(normalized)
                                discovered_urls.append(normalized)
                                if len(discovered_urls) >= max_urls:
                                    logger.info("max_urls_reached", extra={"max_urls": max_urls})
                                    break
                except ET.ParseError as e:
                    logger.error("sitemap_xml_parse_failed", extra={
                        "sitemap_url": sitemap_url,
                        "error": str(e)
                    })
                    fetch_errors.append({"url": sitemap_url, "error": "parse_error"})
                    continue
                    
            except requests.exceptions.Timeout:
                logger.error("sitemap_fetch_timeout", extra={"sitemap_url": sitemap_url})
                fetch_errors.append({"url": sitemap_url, "error": "timeout"})
                continue
            except requests.exceptions.RequestException as e:
                logger.error("sitemap_fetch_exception", extra={
                    "sitemap_url": sitemap_url,
                    "error": str(e)
                })
                fetch_errors.append({"url": sitemap_url, "error": str(e)})
                continue
            except Exception as e:
                logger.error("sitemap_processing_exception", extra={
                    "sitemap_url": sitemap_url,
                    "error": str(e)
                })
                fetch_errors.append({"url": sitemap_url, "error": str(e)})
                continue

        logger.info("sitemap_discovery_complete", extra={
            "base_url": base_url,
            "sitemaps_visited": len(visited_sitemaps),
            "urls_discovered": len(discovered_urls),
            "domain_mismatch_urls_skipped": domain_mismatch_urls,
            "fetch_errors": len(fetch_errors),
            "errors": fetch_errors if fetch_errors else None
        })
        
        span.set_attribute("sitemaps_visited", len(visited_sitemaps))
        span.set_attribute("urls_discovered", len(discovered_urls))
        span.set_attribute("domain_mismatch_urls", domain_mismatch_urls)
        span.set_attribute("fetch_errors", len(fetch_errors))

        return discovered_urls

def _clean_soup_text(soup):
    for script_or_style in soup(["script", "style", "nav", "footer", "header", "form"]):
        script_or_style.decompose()

    text = soup.get_text(separator=" ")
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    cleaned: List[str] = []
    seen = set()
    for line in lines:
        normalized = re.sub(r"\s+", " ", line).strip()
        if not normalized:
            continue
        if _NOISE_LINE_RE.search(normalized):
            continue
        # Drop tiny non-numeric fragments from JS-heavy pages.
        if len(normalized) < 12 and not re.search(r"\d", normalized):
            continue
        # Drop lines with too many menu-like separators and low text signal.
        alpha_chars = sum(ch.isalpha() for ch in normalized)
        if alpha_chars < 6:
            continue

        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(normalized)

    return "\n".join(cleaned)


def _extract_semantic_sections(soup):
    section_keywords = ["service", "product", "faq", "contact", "about", "portfolio", "pricing", "support", "knowledge"]
    sections = []
    seen = set()

    for tag in soup.find_all(["section", "article", "div"]):
        sid = (tag.get("id") or "").strip().lower()
        sclass = " ".join(tag.get("class", [])).strip().lower() if tag.get("class") else ""
        marker = f"{sid} {sclass}".strip()
        if not marker:
            continue

        kind = next((k for k in section_keywords if k in marker), None)
        if not kind:
            continue

        key = sid or kind

        if kind == "contact":
            text = " ".join(tag.get_text(separator=" ", strip=True).split())
        else:
            text = _clean_soup_text(tag)
        normalized_text = text.strip()
        has_contact_signal = kind == "contact" and bool(
            re.search(r"([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[A-Za-z]{2,})|(\+?\d[\d\-\s()]{7,}\d)|\baddress\b", normalized_text, flags=re.IGNORECASE)
        )
        minimum_len = 60 if has_contact_signal else 120
        if len(normalized_text) < minimum_len:
            continue
        if key in seen:
            continue
        seen.add(key)

        title_el = tag.find(["h1", "h2", "h3", "h4"])
        title = title_el.get_text(strip=True) if title_el else key.title()
        sections.append({"key": key, "title": title, "text": text, "kind": kind})

    return sections


def _extract_contact_fallback_section(clean_text: str):
    text = " ".join((clean_text or "").split())
    if not text:
        return None
    if not re.search(r"([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[A-Za-z]{2,})|(\+?\d[\d\-\s()]{7,}\d)|\baddress\b", text, flags=re.IGNORECASE):
        return None

    start = 0
    marker_match = re.search(r"(contact us|reach out|we'd love to hear from you|we care for you)", text, flags=re.IGNORECASE)
    if marker_match:
        start = marker_match.start()

    contact_text = text[start:start + 900].strip()
    if len(contact_text) < 60:
        return None

    return {
        "key": "contact",
        "title": "Contact",
        "text": contact_text,
        "kind": "contact",
    }

def _fetch_page_payload(url, headers, domain, index_sections: bool = True):
    with tracer.start_as_current_span("fetch_page_payload") as span:
        span.set_attribute("url", url)
        span.set_attribute("domain", domain)
        span.set_attribute("index_sections", index_sections)
        
        try:
            logger.debug("page_fetch_start", extra={"url": url})
            fetch_start = time.time()
            response = requests.get(url, headers=headers, timeout=15)
            fetch_elapsed = time.time() - fetch_start
            
            logger.debug("page_fetch_complete", extra={
                "url": url,
                "status_code": response.status_code,
                "content_size": len(response.text),
                "fetch_time_seconds": round(fetch_elapsed, 2)
            })
            span.set_attribute("status_code", response.status_code)
            span.set_attribute("content_size", len(response.text))
            span.set_attribute("fetch_time_seconds", round(fetch_elapsed, 2))
            
            response.raise_for_status()
            
            logger.debug("parsing_html", extra={"url": url, "size_bytes": len(response.text)})
            parse_start = time.time()
            soup = BeautifulSoup(response.text, 'html.parser')
            parse_elapsed = time.time() - parse_start
            
            logger.debug("html_parsed", extra={
                "url": url,
                "parse_time_seconds": round(parse_elapsed, 2)
            })
            span.set_attribute("parse_time_seconds", round(parse_elapsed, 2))
            
            # Extract links for the crawler
            logger.debug("extracting_links", extra={"url": url})
            link_start = time.time()
            new_links = _get_internal_links(soup, url, domain)
            link_elapsed = time.time() - link_start
            
            logger.debug("links_extracted", extra={
                "url": url,
                "links_found": len(new_links),
                "extraction_time_seconds": round(link_elapsed, 2)
            })
            span.set_attribute("links_found", len(new_links))
            
            # Process content
            logger.debug("cleaning_text", extra={"url": url})
            clean_start = time.time()
            clean_text = _clean_soup_text(soup)
            clean_elapsed = time.time() - clean_start
            
            logger.debug("text_cleaned", extra={
                "url": url,
                "clean_text_length": len(clean_text),
                "clean_time_seconds": round(clean_elapsed, 2)
            })
            span.set_attribute("clean_text_length", len(clean_text))
            
            if not clean_text.strip():
                logger.warning("empty_content_after_cleaning", extra={"url": url})
                return None

            title = soup.title.string.strip() if soup.title and soup.title.string else url
            logger.debug("extracted_title", extra={"url": url, "title": title})
            span.set_attribute("title", title[:100])
            
            sections = []
            if index_sections:
                logger.debug("extracting_sections", extra={"url": url})
                section_start = time.time()
                sections = _extract_semantic_sections(soup)
                section_elapsed = time.time() - section_start
                
                logger.debug("sections_extracted", extra={
                    "url": url,
                    "sections_found": len(sections),
                    "section_extraction_time_seconds": round(section_elapsed, 2)
                })
                span.set_attribute("sections_found", len(sections))
                
                if not any(section.get("kind") == "contact" for section in sections):
                    fallback_contact = _extract_contact_fallback_section(clean_text)
                    if fallback_contact:
                        sections.append(fallback_contact)
                        logger.debug("contact_fallback_added", extra={"url": url})

            result = {
                "title": title,
                "normalized_url": _normalize_url(url),
                "clean_text": clean_text,
                "new_links": new_links,
                "sections": sections,
            }
            
            logger.info("page_payload_complete", extra={
                "url": url,
                "title": title,
                "content_length": len(clean_text),
                "links_count": len(new_links),
                "sections_count": len(sections)
            })
            
            return result
            
        except requests.exceptions.Timeout as e:
            logger.error("page_fetch_timeout", extra={"url": url, "error": str(e)})
            span.set_attribute("error_type", "timeout")
            return None
        except requests.exceptions.HTTPError as e:
            logger.error("page_fetch_http_error", extra={
                "url": url,
                "status_code": e.response.status_code,
                "error": str(e)
            })
            span.set_attribute("error_type", "http_error")
            span.set_attribute("http_status", e.response.status_code)
            return None
        except requests.exceptions.RequestException as e:
            logger.error("page_fetch_request_error", extra={"url": url, "error": str(e)})
            span.set_attribute("error_type", "request_exception")
            return None
        except Exception as e:
            logger.error("page_processing_failed", extra={
                "url": url,
                "error": str(e),
                "error_type": type(e).__name__
            })
            span.set_attribute("error_type", "generic_exception")
            span.set_attribute("error_class", type(e).__name__)
            return None


async def _persist_page_payload(payload, tenant_id, db, existing_docs_by_url, budget: Optional[Dict[str, int]] = None):
    created_docs = []
    normalized_url = payload["normalized_url"]
    title = payload["title"]
    clean_text = payload["clean_text"]

    db_doc = existing_docs_by_url.get(normalized_url)
    page_existing_doc = db_doc

    new_docs_created = 0
    if not db_doc:
        if budget is not None and budget.get("remaining", 0) < 1:
            return title, payload["new_links"], 0, 0
        db_doc = DocumentDB(
            title=title,
            source=normalized_url,
            content_snippet=clean_text[:200].replace('\n', ' '),
            tenant_id=tenant_id
        )
        db.add(db_doc)
        db.flush()
        created_docs.append(db_doc)
        new_docs_created += 1
        if budget is not None:
            budget["remaining"] = max(0, budget.get("remaining", 0) - 1)
        existing_docs_by_url[normalized_url] = db_doc

    metadata = {
        "source": normalized_url,
        "doc_id": db_doc.id,
        "title": title,
        "content_type": "page"
    }

    try:
        await asyncio.to_thread(rag_service.ingest_text, clean_text, metadata, collection_name=tenant_id)
        if page_existing_doc:
            page_existing_doc.title = title
            page_existing_doc.content_snippet = clean_text[:200].replace('\n', ' ')

        section_docs_indexed = 0
        for section in payload["sections"]:
            section_source = f"{normalized_url}/__tc_section/{section['key']}"
            sec_doc = existing_docs_by_url.get(section_source)
            section_existing_doc = sec_doc

            if not sec_doc:
                if budget is not None and budget.get("remaining", 0) < 1:
                    break
                sec_doc = DocumentDB(
                    title=f"{title} - {section['title']}",
                    source=section_source,
                    content_snippet=section["text"][:200].replace('\n', ' '),
                    tenant_id=tenant_id
                )
                db.add(sec_doc)
                db.flush()
                created_docs.append(sec_doc)
                existing_docs_by_url[section_source] = sec_doc
                new_docs_created += 1
                if budget is not None:
                    budget["remaining"] = max(0, budget.get("remaining", 0) - 1)

            sec_meta = {
                "source": normalized_url,
                "doc_id": sec_doc.id,
                "title": sec_doc.title,
                "content_type": "section",
                "section_key": section["key"],
                "section_kind": section["kind"],
            }
            await asyncio.to_thread(rag_service.ingest_text, section["text"], sec_meta, collection_name=tenant_id)
            if section_existing_doc:
                section_existing_doc.title = f"{title} - {section['title']}"
                section_existing_doc.content_snippet = section["text"][:200].replace('\n', ' ')
            section_docs_indexed += 1

        return title, payload["new_links"], new_docs_created, section_docs_indexed
    except Exception:
        for doc in created_docs:
            try:
                db.delete(doc)
            except Exception:
                pass
        raise

def _update_crawl_queue(discovered_links, scraped_urls, urls_to_scrape):
    for link in discovered_links:
        if link not in scraped_urls and link not in urls_to_scrape:
            urls_to_scrape.append(link)

@router.post("/scrape")
async def scrape_website(
    request: WebScrapeRequest,
    tenant_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    with tracer.start_as_current_span("scrape_website") as span:
        span.set_attribute("url", request.url)
        span.set_attribute("tenant_id", tenant_id)
        span.set_attribute("max_pages", request.max_pages)
        span.set_attribute("use_sitemaps", request.use_sitemaps)
        
        scrape_start = time.time()
        
        try:
            logger.info("scrape_request_started", extra={
                "url": request.url,
                "tenant_id": tenant_id,
                "max_pages": request.max_pages,
                "use_sitemaps": request.use_sitemaps
            })
            
            base_url = request.url
            if not base_url.startswith(('http://', 'https://')):
                base_url = 'https://' + base_url
            
            base_url = _normalize_url(base_url)
            logger.debug("url_normalized", extra={"original": request.url, "normalized": base_url})
            
            if not is_safe_outbound_url(base_url):
                logger.warning("unsafe_url_rejected", extra={"url": base_url})
                raise HTTPException(status_code=400, detail="Unsafe scrape URL")

            # Attempt to detect and correct domain variant (www vs non-www)
            corrected_url = _detect_correct_domain_variant(base_url)
            if corrected_url:
                base_url = corrected_url
                logger.info("domain_variant_auto_corrected", extra={"original": request.url, "corrected": base_url})
                span.set_attribute("domain_auto_corrected", True)

            domain = urlparse(base_url).netloc
            span.set_attribute("domain", domain)
            span.set_attribute("original_domain", urlparse(request.url).netloc if request.url.startswith(('http://', 'https://')) else "unknown")
            
            logger.debug("domain_extracted", extra={"domain": domain})
            
            max_pages = max(1, min(request.max_pages or 3000, 10000))
            urls_to_scrape = [base_url]
            scraped_urls = set()
            pages_processed = []
            new_docs_count = 0
            failed_pages = 0
            failed_urls = []
            section_docs_indexed = 0
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
            }

            if request.use_sitemaps:
                logger.info("discovering_sitemaps", extra={"url": base_url})
                sitemap_start = time.time()
                
                sitemap_urls = await asyncio.to_thread(
                    _fetch_sitemap_urls,
                    base_url,
                    headers,
                    domain,
                    max_urls=max_pages * 3,
                )
                
                sitemap_elapsed = time.time() - sitemap_start
                logger.info("sitemaps_discovered", extra={
                    "url": base_url,
                    "sitemaps_count": len(sitemap_urls),
                    "discovery_time_seconds": round(sitemap_elapsed, 2)
                })
                span.set_attribute("sitemaps_discovered", len(sitemap_urls))
                
                for sitemap_url in sitemap_urls:
                    if sitemap_url not in urls_to_scrape:
                        urls_to_scrape.append(sitemap_url)

            existing_docs_by_url = _build_existing_web_doc_map(db, tenant_id)
            doc_budget = {"remaining": remaining_document_slots(db, tenant_id)}
            
            logger.info("crawl_preparation_complete", extra={
                "domain": domain,
                "initial_queue_size": len(urls_to_scrape),
                "existing_docs": len(existing_docs_by_url),
                "document_budget": doc_budget["remaining"]
            })
            
            if doc_budget["remaining"] <= 0:
                logger.error("document_quota_exceeded", extra={
                    "tenant_id": tenant_id,
                    "remaining": doc_budget["remaining"]
                })
                raise HTTPException(status_code=403, detail="Document quota exceeded for current plan.")

            crawl_start = time.time()
            while urls_to_scrape and len(scraped_urls) < max_pages:
                url = urls_to_scrape.pop(0)
                if url in scraped_urls:
                    continue
                
                progress = len(scraped_urls) + 1
                logger.info("crawl_item", extra={
                    "url": url,
                    "progress": f"{progress}/{max_pages}",
                    "queue_size": len(urls_to_scrape)
                })
                span.set_attribute(f"crawl_page_{progress}_url", url[:100])
                
                scraped_urls.add(url)
                
                payload_fetch_start = time.time()
                payload = await asyncio.to_thread(
                    _fetch_page_payload,
                    url,
                    headers,
                    domain,
                    request.index_sections,
                )
                payload_fetch_elapsed = time.time() - payload_fetch_start
                
                if payload:
                    logger.debug("page_payload_received", extra={
                        "url": url,
                        "title": payload.get("title"),
                        "content_size": len(payload.get("clean_text", "")),
                        "links_count": len(payload.get("new_links", [])),
                        "payload_fetch_time": round(payload_fetch_elapsed, 2)
                    })
                    
                    persist_start = time.time()
                    title, discovered_links, created_count, sections_count = await _persist_page_payload(
                        payload,
                        tenant_id,
                        db,
                        existing_docs_by_url,
                        doc_budget,
                    )
                    persist_elapsed = time.time() - persist_start
                    
                    logger.debug("page_persisted", extra={
                        "url": url,
                        "title": title,
                        "docs_created": created_count,
                        "sections_indexed": sections_count,
                        "persist_time": round(persist_elapsed, 2),
                        "budget_remaining": doc_budget.get("remaining", 0)
                    })
                else:
                    title, discovered_links, created_count, sections_count = None, [], 0, 0
                    failed_urls.append(url)
                    logger.warning("page_payload_empty", extra={"url": url})
                
                if title:
                    pages_processed.append(title)
                else:
                    failed_pages += 1
                    
                if created_count:
                    new_docs_count += created_count
                    
                section_docs_indexed += sections_count
                    
                _update_crawl_queue(discovered_links, scraped_urls, urls_to_scrape)

            crawl_elapsed = time.time() - crawl_start
            
            if new_docs_count > 0:
                _increment_usage(db, tenant_id, "documents_indexed", amount=new_docs_count)

            db.commit()
            
            logger.info("crawl_completed", extra={
                "domain": domain,
                "pages_scraped": len(pages_processed),
                "pages_failed": failed_pages,
                "failed_urls": failed_urls if failed_urls else None,
                "new_docs_indexed": new_docs_count,
                "section_docs_indexed": section_docs_indexed,
                "unique_urls_discovered": len(scraped_urls),
                "crawl_time_seconds": round(crawl_elapsed, 2),
                "average_page_time": round(crawl_elapsed / max(1, len(scraped_urls)), 2)
            })
            
            span.set_attribute("pages_scraped", len(pages_processed))
            span.set_attribute("pages_failed", failed_pages)
            span.set_attribute("new_docs_indexed", new_docs_count)
            span.set_attribute("section_docs_indexed", section_docs_indexed)
            span.set_attribute("urls_discovered", len(scraped_urls))
            
            if not pages_processed:
                logger.error("no_readable_content", extra={
                    "url": base_url,
                    "domain": domain,
                    "pages_attempted": len(scraped_urls)
                })
                raise HTTPException(status_code=400, detail="No readable content found on the website")
            
            total_elapsed = time.time() - scrape_start
            logger.info("scrape_request_completed", extra={
                "url": request.url,
                "tenant_id": tenant_id,
                "total_time_seconds": round(total_elapsed, 2),
                "status": "success"
            })
            
            span.set_attribute("total_time_seconds", round(total_elapsed, 2))
                
            return {
                "status": "success", 
                "pages_scraped": len(pages_processed),
                "pages_discovered": len(scraped_urls),
                "new_pages_indexed": new_docs_count,
                "failed_pages": failed_pages,
                "section_docs_indexed": section_docs_indexed,
                "max_pages": max_pages,
                "titles": pages_processed[:5]
            }
        
        except HTTPException as he:
            logger.info("scrape_request_http_error", extra={
                "url": request.url,
                "tenant_id": tenant_id,
                "status_code": he.status_code,
                "detail": he.detail
            })
            db.rollback()
            span.set_attribute("http_error_status", he.status_code)
            raise
            
        except requests.exceptions.RequestException as e:
            total_elapsed = time.time() - scrape_start
            logger.error("scrape_network_error", extra={
                "url": request.url,
                "tenant_id": tenant_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "elapsed_time": round(total_elapsed, 2)
            })
            db.rollback()
            span.set_attribute("error_type", "request_exception")
            raise HTTPException(status_code=400, detail=f"Failed to fetch website: {str(e)}")
            
        except Exception as e:
            total_elapsed = time.time() - scrape_start
            logger.error("scrape_unexpected_error", extra={
                "url": request.url,
                "tenant_id": tenant_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "elapsed_time": round(total_elapsed, 2)
            })
            db.rollback()
            span.set_attribute("error_type", "generic_exception")
            span.set_attribute("error_class", type(e).__name__)
            raise HTTPException(status_code=500, detail=str(e))
