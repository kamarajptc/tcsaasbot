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

from app.services.rag_service import rag_service
from app.core.security import get_current_user_id
from app.core.database import get_db, DocumentDB, TenantUsageDB
from app.core.logging import logger
from app.core.usage_limits import check_document_quota, remaining_document_slots
from app.core.config import get_settings
from app.core.url_security import is_safe_outbound_url

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
    return _canonical_host(a) == _canonical_host(b)

def _host_variants(host: str) -> List[str]:
    host = (host or "").strip().lower()
    if not host:
        return []
    if host.startswith("www."):
        return [host, host[4:]]
    return [host, f"www.{host}"]


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

    def maybe_add(raw_url: str):
        full_url = urljoin(base_url, raw_url)
        parsed_full = urlparse(full_url)
        if not _same_domain(parsed_full.netloc, domain) or parsed_full.fragment:
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
    try:
        parsed = urlparse(base_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        response = requests.get(robots_url, headers=headers, timeout=8)
        if response.status_code != 200:
            return []
        sitemaps = []
        for line in response.text.splitlines():
            if line.lower().startswith("sitemap:"):
                sitemap_url = line.split(":", 1)[1].strip()
                if sitemap_url:
                    sitemaps.append(sitemap_url)
        return sitemaps
    except Exception:
        return []


def _fetch_sitemap_urls(base_url: str, headers: Dict[str, str], domain: str, max_urls: int = 30000) -> List[str]:
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

    sitemap_queue = list(seed_sitemaps)
    visited_sitemaps = set()
    discovered_urls = []
    seen_urls = set()

    while sitemap_queue and len(discovered_urls) < max_urls:
        sitemap_url = sitemap_queue.pop(0)
        if sitemap_url in visited_sitemaps:
            continue
        visited_sitemaps.add(sitemap_url)

        try:
            response = requests.get(sitemap_url, headers=headers, timeout=12)
            if response.status_code != 200:
                continue

            content = response.content
            if sitemap_url.endswith(".gz"):
                try:
                    content = gzip.decompress(content)
                except Exception:
                    continue

            root = ET.fromstring(content)
            root_tag = root.tag.lower()
            is_index = root_tag.endswith("sitemapindex")

            for loc in root.findall(".//{*}loc"):
                loc_url = (loc.text or "").strip()
                if not loc_url:
                    continue
                parsed_loc = urlparse(loc_url)
                if not _same_domain(parsed_loc.netloc, domain):
                    continue

                normalized = _normalize_url(loc_url)
                if is_index:
                    if normalized not in visited_sitemaps:
                        sitemap_queue.append(normalized)
                else:
                    if normalized not in seen_urls:
                        seen_urls.add(normalized)
                        discovered_urls.append(normalized)
                        if len(discovered_urls) >= max_urls:
                            break
        except Exception:
            continue

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
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract links for the crawler
        new_links = _get_internal_links(soup, url, domain)
        
        # Process content
        clean_text = _clean_soup_text(soup)
        if not clean_text.strip():
            return None

        title = soup.title.string.strip() if soup.title and soup.title.string else url
        sections = _extract_semantic_sections(soup) if index_sections else []
        if index_sections and not any(section.get("kind") == "contact" for section in sections):
            fallback_contact = _extract_contact_fallback_section(clean_text)
            if fallback_contact:
                sections.append(fallback_contact)

        return {
            "title": title,
            "normalized_url": _normalize_url(url),
            "clean_text": clean_text,
            "new_links": new_links,
            "sections": sections,
        }
    except Exception as e:
        logger.error(f"Failed to process page {url}: {str(e)}")
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
    try:
        base_url = request.url
        if not base_url.startswith(('http://', 'https://')):
            base_url = 'https://' + base_url
        base_url = _normalize_url(base_url)
        if not is_safe_outbound_url(base_url):
            raise HTTPException(status_code=400, detail="Unsafe scrape URL")

        domain = urlparse(base_url).netloc
        
        max_pages = max(1, min(request.max_pages or 3000, 10000))
        urls_to_scrape = [base_url]
        scraped_urls = set()
        pages_processed = []
        new_docs_count = 0
        failed_pages = 0
        section_docs_indexed = 0
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }

        if request.use_sitemaps:
            sitemap_urls = await asyncio.to_thread(
                _fetch_sitemap_urls,
                base_url,
                headers,
                domain,
                max_urls=max_pages * 3,
            )
            for sitemap_url in sitemap_urls:
                if sitemap_url not in urls_to_scrape:
                    urls_to_scrape.append(sitemap_url)

        existing_docs_by_url = _build_existing_web_doc_map(db, tenant_id)
        doc_budget = {"remaining": remaining_document_slots(db, tenant_id)}
        if doc_budget["remaining"] <= 0:
            raise HTTPException(status_code=403, detail="Document quota exceeded for current plan.")

        while urls_to_scrape and len(scraped_urls) < max_pages:
            url = urls_to_scrape.pop(0)
            if url in scraped_urls: continue
                
            logger.info(f"Crawl item: {url} ({len(scraped_urls)}/{max_pages})")
            scraped_urls.add(url)
            
            payload = await asyncio.to_thread(
                _fetch_page_payload,
                url,
                headers,
                domain,
                request.index_sections,
            )
            if payload:
                title, discovered_links, created_count, sections_count = await _persist_page_payload(
                    payload,
                    tenant_id,
                    db,
                    existing_docs_by_url,
                    doc_budget,
                )
            else:
                title, discovered_links, created_count, sections_count = None, [], 0, 0
            
            if title:
                pages_processed.append(title)
            else:
                failed_pages += 1
            if created_count:
                new_docs_count += created_count
            section_docs_indexed += sections_count
                
            _update_crawl_queue(discovered_links, scraped_urls, urls_to_scrape)

        if new_docs_count > 0:
            _increment_usage(db, tenant_id, "documents_indexed", amount=new_docs_count)

        db.commit()
        
        if not pages_processed:
            raise HTTPException(status_code=400, detail="No readable content found on the website")
            
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
        
    except HTTPException:
        db.rollback()
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to fetch website: {str(e)}")
    except Exception as e:
        logger.error(f"Scraper error: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
