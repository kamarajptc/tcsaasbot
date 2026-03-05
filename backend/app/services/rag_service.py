import os
import time
import re
import hashlib
from collections import Counter
from typing import List, Dict, Optional, Literal, Tuple

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from qdrant_client import QdrantClient
from app.core.config import get_settings
from app.core.logging import logger
from app.core.telemetry import get_tracer
from app.services.qdrant_store import QdrantCollectionStore

settings = get_settings()
tracer = get_tracer("rag_service")


class LocalHashEmbeddings:
    """Deterministic local embeddings for CI/offline validation."""

    def __init__(self, dims: int = 96):
        self.dims = dims

    def _vector(self, text: str) -> List[float]:
        digest = hashlib.sha256((text or "").encode("utf-8")).digest()
        values: List[float] = []
        for i in range(self.dims):
            b = digest[i % len(digest)]
            values.append((b / 255.0) * 2.0 - 1.0)
        return values

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._vector(text)


class OfflineValidationLLM:
    """Fail-fast placeholder for localhash validation mode."""

    def invoke(self, *_args, **_kwargs):
        raise RuntimeError("LLM-backed reasoning is unavailable when LLM_PROVIDER=localhash.")


def _get_llm():
    """Get the LLM based on the configured provider."""
    if settings.LLM_PROVIDER == "localhash":
        return OfflineValidationLLM()
    if settings.LLM_PROVIDER == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0.3,
            retries=0,
            convert_system_message_to_human=True,
        )
    else:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            openai_api_key=settings.OPENAI_API_KEY,
            model="gpt-4o-mini",
            temperature=0.3,
        )


def _get_embeddings():
    """Get embeddings based on the configured provider."""
    if settings.LLM_PROVIDER == "localhash":
        return LocalHashEmbeddings()
    if settings.LLM_PROVIDER == "gemini":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        return GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001",
            google_api_key=settings.GOOGLE_API_KEY,
        )
    else:
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(
            openai_api_key=settings.OPENAI_API_KEY,
            model="text-embedding-3-small",
        )


class RAGService:
    def __init__(self):
        self.embeddings = _get_embeddings()
        self.persist_directory = settings.QDRANT_PATH
        os.makedirs(self.persist_directory, exist_ok=True)
        self._client = QdrantClient(path=self.persist_directory)
        logger.info("rag_service_initialized", extra={
            "persist_directory": self.persist_directory,
            "llm_provider": settings.LLM_PROVIDER,
        })
        
    def _sanitize_collection_name(self, name: str) -> str:
        # Replace @ with _at_ specifically for emails
        name = name.replace("@", "_at_")
        # Replace non-alphanumeric chars (except _ and - and .) with _
        name = re.sub(r'[^a-zA-Z0-9._-]', '_', name)
        
        # Ensure it starts and ends with alphanumeric
        if not re.match(r'^[a-zA-Z0-9]', name):
            name = "c" + name
        if not re.match(r'.*[a-zA-Z0-9]$', name):
            name = name + "c"
            
        # Truncate to 63 chars to keep collection names backend-safe.
        if len(name) > 63:
            name = name[:63]
            # Re-check end
            if not re.match(r'.*[a-zA-Z0-9]$', name):
                name = name[:-1] + "c"
        
        # Min length 3
        if len(name) < 3:
            name = name.ljust(3, '_')
            
        return name

    def get_vector_store(self, collection_name: str):
        safe_collection_name = self._sanitize_collection_name(collection_name)
        return QdrantCollectionStore(
            client=self._client,
            collection_name=safe_collection_name,
            embeddings=self.embeddings,
        )

    def _build_splitter(self) -> RecursiveCharacterTextSplitter:
        """Use structure-aware separators to improve semantic chunks."""
        return RecursiveCharacterTextSplitter(
            chunk_size=settings.RAG_CHUNK_SIZE,
            chunk_overlap=settings.RAG_CHUNK_OVERLAP,
            separators=["\n## ", "\n### ", "\n\n", "\n", ". ", " ", ""],
            length_function=len,
        )

    def _infer_page_type(self, metadata: Dict) -> str:
        title = (metadata or {}).get("title", "") or ""
        source = (metadata or {}).get("source", "") or ""
        combined = f"{title} {source}".lower()
        if any(token in combined for token in (
            "/contact", "#contact", "__tc_section/contact", "contact us", "contact-us", "reach us", "contact section"
        )):
            return "contact"
        if any(token in combined for token in (
            "/about", "#about", "__tc_section/about", "about us", "/team", "our team", "leadership", "company overview", "about section"
        )):
            return "about"
        if any(token in combined for token in (
            "/pricing", "__tc_section/pricing", "pricing", "plans", "plan comparison", "bestpricing"
        )):
            return "pricing"
        if any(token in combined for token in (
            "/services", "__tc_section/services", "our services", "ourservices", "solutions", "capabilities", "service list"
        )):
            return "services"
        if any(token in combined for token in ("/product", "/products", "catalog", "catalogue")):
            return "product"
        if any(token in combined for token in ("/faq", "faq", "help center", "support")):
            return "faq"
        if any(token in combined for token in ("/blog", "blog", "privacy", "terms", "policy")):
            return "low_signal"
        return "general"

    def _looks_like_heading(self, line: str) -> bool:
        stripped = (line or "").strip()
        if not stripped:
            return False
        if stripped.startswith(("#", "##", "###")):
            return True
        if len(stripped) > 90:
            return False
        if stripped.endswith(":"):
            return True
        words = stripped.split()
        if len(words) > 8:
            return False
        letters = [word for word in words if re.search(r"[A-Za-z]", word)]
        if not letters:
            return False
        title_case_ratio = sum(1 for word in letters if word[:1].isupper()) / max(len(letters), 1)
        return title_case_ratio >= 0.7

    def _split_into_sections(self, text: str) -> List[Tuple[str, str, str]]:
        lines = [line.strip() for line in (text or "").splitlines()]
        sections: List[Tuple[str, str, str]] = []
        current_heading = "general"
        current_kind = "body"
        buffer: List[str] = []

        def flush():
            nonlocal buffer
            body = "\n".join(part for part in buffer if part).strip()
            if body:
                sections.append((body, current_heading, current_kind))
            buffer = []

        for line in lines:
            if not line:
                if buffer and buffer[-1] != "":
                    buffer.append("")
                continue
            if self._looks_like_heading(line):
                flush()
                current_heading = re.sub(r"^#+\s*", "", line).strip().lower() or "general"
                current_kind = "heading_block"
                buffer.append(line)
                continue
            buffer.append(line)
        flush()
        return sections or [(text.strip(), "general", "body")]

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"[a-z0-9]{3,}", (text or "").lower())

    def _question_intent(self, question: str) -> str:
        q = (question or "").lower()
        if any(token in q for token in ("phone", "contact number", "contact no", "email", "mail id", "mail address", "address", "where is", "location", "call")):
            return "contact"
        if any(token in q for token in ("founder", "ceo", "owner", "leadership", "who is", "about")):
            return "leadership"
        if any(token in q for token in ("price", "pricing", "plan", "subscription", "cost")):
            return "pricing"
        if any(token in q for token in ("services", "solutions", "offerings", "what do you provide")):
            return "services"
        if any(token in q for token in ("product", "catalog", "tile", "floor", "wall", "bathroom")):
            return "product"
        return "general"

    def _preferred_page_types(self, intent: str) -> tuple[str, ...]:
        mapping = {
            "contact": ("contact", "about"),
            "leadership": ("about",),
            "pricing": ("pricing",),
            "services": ("services", "about"),
            "product": ("product",),
            "general": (),
        }
        return mapping.get(intent, ())

    def _page_type(self, metadata: Dict) -> str:
        stored = ((metadata or {}).get("page_type") or "").strip().lower()
        if stored and stored != "general":
            return stored
        return self._infer_page_type(metadata or {}).lower()

    def _corpus_scan_docs(self, vector_store, intent: str) -> List[Document]:
        try:
            docs = vector_store.get_all_documents(limit=2048)
        except Exception:
            return []
        preferred = self._preferred_page_types(intent)
        if not preferred:
            return docs
        preferred_docs = []
        for doc in docs:
            page_type = self._page_type(doc.metadata or {})
            if page_type in preferred:
                preferred_docs.append(doc)
        return preferred_docs or docs

    def _extract_contact_facts(self, docs: List[Document]) -> Dict[str, Optional[str]]:
        text = " ".join(" ".join((doc.page_content or "").split()) for doc in docs)

        def first(pattern: str):
            match = re.search(pattern, text, flags=re.IGNORECASE)
            return match.group(1).strip() if match else None

        phone = first(r"phone[:\-\s]*?(\+?\d[\d\-\s()]{7,}\d)")
        if not phone:
            phone = first(r"(\+?\d[\d\-\s()]{7,}\d)")
        email = first(r"([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[A-Za-z]{2,})")
        address = first(r"address[:\-\s]*([^.;]{6,220})")
        return {"phone": phone, "email": email, "address": address}

    def _hybrid_rank_scored_docs(
        self,
        question: str,
        scored_docs: List[Tuple[Document, float]],
    ) -> List[Tuple[Document, float]]:
        if not scored_docs:
            return []
        query_tokens = Counter(self._tokenize(question))
        intent = self._question_intent(question)
        preferred_types = self._preferred_page_types(intent)

        def rank(item: Tuple[Document, float]) -> float:
            doc, score = item
            meta = doc.metadata or {}
            page_type = self._page_type(meta)
            text = doc.page_content or ""
            doc_tokens = Counter(self._tokenize(
                f"{meta.get('title', '')} {meta.get('source', '')} {text[:600]}"
            ))
            lexical_overlap = sum(min(query_tokens[token], doc_tokens[token]) for token in query_tokens)
            lexical_score = min(lexical_overlap / max(len(query_tokens), 1), 1.0)
            bonus = 0.0
            if page_type == intent or (preferred_types and page_type in preferred_types):
                bonus += 0.35
            if intent == "leadership" and page_type == "contact":
                bonus -= 0.12
            if page_type == "low_signal":
                bonus -= 0.25
            if int(meta.get("chunk_index") or 0) == 0:
                bonus += 0.04
            if self._is_identity_query(question) and any(marker in text.lower() for marker in ("founded", "company", "professional services", "industry experts")):
                bonus += 0.12
            return float(score or 0.0) + lexical_score * 0.45 + bonus

        ranked = sorted(scored_docs, key=rank, reverse=True)
        if preferred_types:
            preferred = [
                item for item in ranked
                if self._page_type(item[0].metadata or {}) in preferred_types
            ]
            if preferred:
                spillover = [item for item in ranked if item not in preferred]
                return preferred + spillover
        return ranked

    def _expand_with_adjacent_chunks(
        self,
        vector_store,
        ranked_docs: List[Tuple[Document, float]],
        question: str,
        limit: int,
    ) -> List[Document]:
        expanded: List[Document] = []
        seen = set()

        def add_doc(doc: Document):
            meta = doc.metadata or {}
            key = (
                meta.get("doc_id"),
                meta.get("source"),
                meta.get("chunk_index"),
            )
            if key in seen:
                return
            seen.add(key)
            expanded.append(doc)

        for doc, _ in ranked_docs[:limit]:
            add_doc(doc)

        # Fact queries need higher precision, so keep expansion narrow.
        adjacency_window = 1 if self._is_fact_query(question) else 2
        max_seed_docs = 2 if self._is_fact_query(question) else 3

        for doc, _ in ranked_docs[:max_seed_docs]:
            meta = doc.metadata or {}
            chunk_index = meta.get("chunk_index")
            if chunk_index is None:
                continue
            all_chunks = vector_store.get_document_chunks(
                doc_id=meta.get("doc_id"),
                source=meta.get("source"),
            )
            if not all_chunks:
                continue
            for neighbor in all_chunks:
                neighbor_index = int((neighbor.metadata or {}).get("chunk_index") or 0)
                if abs(neighbor_index - int(chunk_index)) <= adjacency_window:
                    add_doc(neighbor)

        return expanded[: max(limit + 2, limit)]

    def _retrieve_ranked_docs(self, vector_store, question: str, retrieval_k: int, fetch_k: int) -> List[Document]:
        scored_docs = vector_store.similarity_search_with_relevance_scores(question, k=fetch_k)
        if not scored_docs:
            return []
        threshold = settings.RAG_RETRIEVAL_SCORE_THRESHOLD
        filtered = [(doc, score) for doc, score in scored_docs if score is None or score >= threshold]
        ranked = self._hybrid_rank_scored_docs(question, filtered or scored_docs)
        return self._expand_with_adjacent_chunks(vector_store, ranked, question, retrieval_k)

    def _normalize_ingest_text(self, text: str) -> str:
        cleaned = re.sub(r"\r\n?", "\n", text or "")
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    def _is_fact_query(self, question: str) -> bool:
        q = (question or "").lower()
        tokens = [
            "what is", "phone", "email", "contact", "rate limit", "api limit",
            "address", "price", "pricing", "plan", "how much", "who is",
        ]
        return any(t in q for t in tokens)

    def _retrieval_k(self, question: str) -> int:
        base = max(3, settings.RAG_RETRIEVAL_K)
        if self._is_fact_query(question):
            return min(base, 5)
        if len((question or "").split()) >= 12:
            return min(base + 2, 10)
        return base

    def ingest_text(self, text: str, metadata: Dict, collection_name: str = "default"):
        with tracer.start_as_current_span("rag_ingest") as span:
            span.set_attribute("collection", collection_name)
            span.set_attribute("text_length", len(text))

            start = time.perf_counter()
            prepared_text = self._normalize_ingest_text(text)
            text_splitter = self._build_splitter()
            docs = []
            page_type = self._infer_page_type(metadata or {})
            sections = self._split_into_sections(prepared_text)
            section_chunks: List[Tuple[str, str, str]] = []
            for section_text, section_key, section_kind in sections:
                split_chunks = text_splitter.split_text(section_text)
                for chunk in split_chunks:
                    if chunk.strip():
                        section_chunks.append((chunk, section_key, section_kind))
            for idx, (chunk, section_key, section_kind) in enumerate(section_chunks):
                chunk_meta = dict(metadata or {})
                chunk_meta.update({
                    "chunk_index": idx,
                    "chunk_count": len(section_chunks),
                    "section_key": section_key,
                    "section_kind": section_kind,
                    "page_type": page_type,
                })
                docs.append(Document(page_content=chunk, metadata=chunk_meta))
            vector_store = self.get_vector_store(collection_name)
            vector_store.add_documents(docs)
            duration_ms = round((time.perf_counter() - start) * 1000, 2)

            span.set_attribute("chunks_added", len(docs))
            span.set_attribute("duration_ms", duration_ms)

            logger.info("rag_ingest_completed", extra={
                "collection": collection_name,
                "chunks_added": len(docs),
                "text_length": len(prepared_text),
                "chunk_size": settings.RAG_CHUNK_SIZE,
                "chunk_overlap": settings.RAG_CHUNK_OVERLAP,
                "duration_ms": duration_ms,
            })
            return {"status": "success", "chunks_added": len(docs)}

    def delete_document(self, doc_id: int, collection_name: str = "default"):
        vector_store = self.get_vector_store(collection_name)
        vector_store.delete_by_doc_id(doc_id)
        logger.info("rag_document_deleted", extra={
            "doc_id": doc_id, "collection": collection_name
        })
        return {"status": "success"}

    def _build_behavior_prompt(self, bot_instructions: str = "", bot_name: Optional[str] = None) -> str:
        bot_instructions = (bot_instructions or "").strip()
        identity_line = f"You are {bot_name}, a configured customer support assistant." if bot_name else "You are a configured customer support assistant."
        return (
            f"{identity_line} Follow this configured bot behavior and tone:\n"
            f"{bot_instructions or 'Be helpful, concise, and professional.'}\n\n"
            "Response policy:\n"
            "1. Answer from retrieved context first.\n"
            "2. Do not dump raw chunks or long copied snippets.\n"
            "3. For direct fact questions (phone, email, pricing, limits, address), give a direct one-line answer first.\n"
            "4. If the exact fact is not found in retrieved context, clearly say it is not available in indexed knowledge and ask one useful follow-up.\n"
            "5. Treat historical chat transcript style statements as lower confidence than official policy or contact details pages.\n"
            "6. Never output raw copied chunks. Always rewrite in clean, complete sentences.\n"
            "7. Avoid repeated words/phrases and avoid unfinished trailing text.\n"
            "8. Always sound like a calm, polite customer support assistant.\n"
            "9. If the user is vague, ask one short clarifying question instead of guessing.\n"
            "10. If the request is outside scope, politely redirect them to supported topics.\n"
        )

    def _clean_answer_text(self, text: str) -> str:
        value = " ".join((text or "").split()).strip()
        if not value:
            return value
        # Fix common mojibake seen in crawled pages.
        value = value.replace("â", "'").replace("â€“", "-").replace("â€”", "-")
        # Remove common website CTA/UI fragments that pollute scraped text.
        value = re.sub(
            r"\b(Read more|View More|Request a call back|Quick View|Filter|Sort by)\b.*$",
            "",
            value,
            flags=re.IGNORECASE,
        ).strip(" ,;:-")
        value = re.sub(
            r"\b(Where to use|Material|Finish|Concept|Color|Size)\b.*$",
            "",
            value,
            flags=re.IGNORECASE,
        ).strip(" ,;:-")
        value = re.sub(r"\b\d+\s*Ft\b(?:\s+\d+\s*Ft\b)+", "", value, flags=re.IGNORECASE).strip()
        value = re.sub(r"\bHome\s*/\s*[^.]+$", "", value, flags=re.IGNORECASE).strip(" ,;:-")
        # Collapse immediate repeated phrases (e.g. "Our Services Our Services ...").
        value = re.sub(r"\b(.{3,40}?)\s+\1\b", r"\1", value, flags=re.IGNORECASE)
        # Remove repeated adjacent words.
        value = re.sub(r"\b(\w+)\s+\1\b", r"\1", value, flags=re.IGNORECASE)
        if not value:
            return ""
        # Keep responses concise and avoid raw chunk-like walls of text.
        if len(value) > 900:
            value = value[:900].rsplit(" ", 1)[0].rstrip(" ,;:") + "..."
        if value[-1] not in ".!?":
            value += "."
        return value

    def _normalize_support_tone(self, text: str) -> str:
        value = self._clean_answer_text(text)
        if not value:
            return value

        replacements = {
            "current knowledge ledger": "the information currently available to me",
            "knowledge ledger": "the information currently available to me",
            "currently indexed knowledge": "the information currently available to me",
            "indexed knowledge": "the information currently available to me",
            "retrieved context": "the information I have available",
            "retrieved content": "the information I have available",
        }
        for old, new in replacements.items():
            value = re.sub(re.escape(old), new, value, flags=re.IGNORECASE)

        if value.startswith("I could not find relevant information"):
            return self._support_fallback(
                "the details for that request",
                "Please ask in a slightly more specific way and I’ll do my best to help."
            )
        if value.startswith("I found relevant knowledge"):
            return self._support_fallback(
                "a clear answer for that request",
                "Please try asking in a more specific way and I’ll do my best to help."
            )
        if value.startswith("I found entries in the ledger"):
            return self._support_fallback(
                "a readable answer for that request",
                "Please try asking in a more specific way and I’ll do my best to help."
            )
        if value == "The question is not relevant.":
            return self._not_relevant_answer()

        return value

    def _response(self, answer: str, sources: List[Dict]) -> Dict:
        return {
            "answer": self._normalize_support_tone(answer),
            "sources": self._format_sources(sources),
        }

    def _classify_question_scenario(self, question: str) -> Literal["positive", "neutral", "negative"]:
        q = (question or "").strip().lower().replace("’", "'")
        if not q:
            return "neutral"

        off_topic_markers = (
            "cricket", "football", "weather", "bitcoin", "crypto", "pizza", "pasta",
            "stock price", "prime minister", "poem", "car should i buy", "fixtures",
            "yesterday's match", "tomorrow's football", "near me",
        )
        if any(token in q for token in off_topic_markers):
            return "negative"

        negative_patterns = (
            r"\bstupid\b",
            r"\bidiot\b",
            r"\buseless\b",
            r"\bdamn\b",
            r"\bshit\b",
            r"\bfuck\b",
            r"\bnonsense\b",
            r"\btrash\b",
            r"\bhell\b",
            r"\bnot helping\b",
        )
        if any(re.search(pattern, q) for pattern in negative_patterns):
            return "negative"

        neutral_patterns = (
            "can you help",
            "tell me more",
            "more details",
            "more info",
            "can you explain",
            "explain more",
            "what else",
            "anything else",
            "guide me",
            "assist me",
            "support me",
            "good morning",
            "good evening",
            "what information can you share",
            "i want to know more",
            "please explain",
            "where should i start",
            "point me in the right direction",
            "looking for some information",
            "walk me through it",
            "clarify",
            "start with the basics",
            "i have a question",
        )
        if q in {"hi", "hello", "hey", "help", "help me", "details", "good morning", "good evening", "need details"}:
            return "neutral"
        if re.fullmatch(r"(hi|hello|hey)\b.*", q):
            return "neutral"
        if any(phrase in q for phrase in neutral_patterns):
            return "neutral"
        if any(q.startswith(token) for token in (
            "can you help", "tell me more", "can you explain", "can you guide", "can you assist", "what can you help"
        )):
            return "neutral"
        unsupported_markers = (
            "hack", "password", "bypass security", "malware", "attack a server", "steal data",
            "break into", "exploit a login", "crack a wifi", "scam users",
        )
        if any(token in q for token in unsupported_markers):
            return "negative"
        return "positive"

    def _negative_reason(self, question: str) -> str:
        q = (question or "").strip().lower().replace("’", "'")
        if any(re.search(pattern, q) for pattern in (
            r"\bstupid\b",
            r"\bidiot\b",
            r"\buseless\b",
            r"\bdamn\b",
            r"\bshit\b",
            r"\bfuck\b",
            r"\bnonsense\b",
            r"\btrash\b",
            r"\bnot helping\b",
            r"\bhell\b",
        )):
            return "abusive"
        if any(token in q for token in (
            "hack", "password", "bypass security", "malware", "attack a server", "steal data",
            "break into", "exploit a login", "crack a wifi", "scam users",
        )):
            return "unsafe"
        return "off_topic"

    def _neutral_answer(self, question: str) -> str:
        q = (question or "").strip().lower()
        if any(token in q for token in ("hi", "hello", "hey")):
            return "Hello. I’m here to help. You can ask me about our company, services, pricing, contact details, or support topics."
        return "I’d be happy to help. Could you tell me whether you need information about our company, services, pricing, contact details, or support?"

    def _negative_answer(self, question: str) -> str:
        reason = self._negative_reason(question)
        if reason == "unsafe":
            return (
                "I can’t help with hacking, bypassing security, password theft, malware, or any harmful activity. "
                "I’m here to help with company, service, pricing, contact, product, and support questions."
            )
        if reason == "abusive":
            return (
                "I’m here to help. If something isn’t working, please tell me what you need about our company, "
                "services, pricing, contact details, products, or support questions, and I’ll assist you."
            )
        return (
            "I’m here to help with company, service, pricing, contact, product, and support questions. "
            "If you’d like, please ask one of those and I’ll assist you."
        )

    def _format_sources(self, raw_sources: List[Dict]) -> List[Dict]:
        formatted: List[Dict] = []
        seen = set()
        for src in raw_sources or []:
            if not isinstance(src, dict):
                continue
            item = {
                "doc_id": src.get("doc_id"),
                "title": src.get("title"),
                "source": src.get("source"),
                "content_type": src.get("content_type", "page"),
                "section_key": src.get("section_key"),
                "section_kind": src.get("section_kind"),
            }
            dedupe_key = (item.get("doc_id"), item.get("source"), item.get("section_key"))
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            formatted.append(item)
        return formatted[:5]

    def _heuristic_compose_answer(self, question: str, snippets: List[str]) -> str:
        lines = []
        for raw in snippets:
            parts = re.split(r"(?<=[.!?])\s+", raw)
            for p in parts:
                t = self._clean_answer_text(p)
                if len(t) < 25:
                    continue
                if any(t.lower() == x.lower() for x in lines):
                    continue
                lines.append(t)
                if len(lines) >= 3:
                    break
            if len(lines) >= 3:
                break
        if not lines:
            return "I found relevant knowledge, but I could not extract a clean summary yet. Please ask for a specific category like products, services, or pricing."
        if "service" in question.lower():
            return "Here are the services currently listed in our indexed knowledge: " + " ".join(lines)
        return " ".join(lines)

    def _support_fallback(self, detail: str, next_step: str = "") -> str:
        answer = f"Sorry, I couldn't find {detail} in the information currently available to me."
        if next_step:
            answer += f" {next_step}"
        return answer

    def _not_relevant_answer(self) -> str:
        return (
            "I’m here to help with company, service, pricing, contact, product, and support questions. "
            "That request doesn’t seem related to the information I currently support."
        )

    def _is_identity_query(self, question: str) -> bool:
        q = (question or "").strip().lower()
        if any(token in q for token in (
            "top selling", "best selling", "most selling", "top ", "pricing", "price",
            "phone", "email", "contact", "address", "location", "services", "solutions", "offerings",
            "founder", "co-founder", "ceo", "owner", "leadership",
            "company profile", "what does your company do", "tell me about your company",
            "what kind of company", "business about",
            "validation code", "support alias", "test marker", "official website",
            "business category", "brand keyword", "primary knowledge domain", "which domain",
        )):
            return False
        return bool(re.search(r"\b(what is|who is|tell me about|about)\b", q))

    def _rank_ledger_docs(self, question: str, docs: List[Document]) -> List[Document]:
        """Prefer profile/about pages for identity-style questions."""
        if not docs:
            return docs
        if not self._is_identity_query(question):
            return docs

        demote_markers = ("cookie", "privacy", "terms", "contact", "blog", "calendly")

        def score(doc: Document) -> int:
            meta = doc.metadata or {}
            title = (meta.get("title") or "").lower()
            source = (meta.get("source") or "").lower()
            text = (doc.page_content or "").lower()

            value = 0
            if "/about" in source or "about us" in title:
                value += 8
            if source.rstrip("/") in ("https://adamsbridge.com", "http://adamsbridge.com"):
                value += 6
            if any(x in text for x in ("founded", "professional services", "company", "industry experts")):
                value += 3
            if any(marker in title or marker in source for marker in demote_markers):
                value -= 6
            return value

        return sorted(docs, key=score, reverse=True)

    def _extract_service_candidates(self, doc_text: str) -> List[str]:
        candidates: List[str] = []
        lower_text = doc_text.lower()

        # Pattern: "Web Design We excel in..."
        contextual_matches = re.findall(
            r"\b([A-Z][A-Za-z0-9&+\- ]{1,36}?)\s+We excel in\b",
            doc_text,
        )
        candidates.extend([m.strip() for m in contextual_matches])

        # Pattern: "Web Design", "Cloud Migration", etc.
        keyword_matches = re.findall(
            r"\b([A-Z][A-Za-z0-9&+\- ]{1,36}\s(?:Design|Development|Consulting|Implementation|Integration|Support|Migration|Automation|Analytics|Engineering))\b",
            doc_text,
        )
        candidates.extend([m.strip() for m in keyword_matches])

        # Pattern: "Product / Architecture / Design / Development"
        slash_matches = re.findall(
            r"\b([A-Z][A-Za-z0-9&+\- ]{1,34})\s*/\s*(?:Architecture|Architecure|Design|Development)\b",
            doc_text,
        )
        candidates.extend([m.strip() for m in slash_matches])

        # Known heading-like service names.
        heading_matches = re.findall(
            r"\b(Web Design|Cloud Services|CRM Development|ERP Development|AI Development|Product Development)\b",
            doc_text,
            flags=re.IGNORECASE,
        )
        candidates.extend([m.strip().title() for m in heading_matches])

        known_phrases = [
            "web design",
            "graphic design",
            "web development",
            "cloud migration",
            "cloud architecture",
            "cloud services",
            "cloud storage",
            "cloud training",
            "seo & digital marketing",
            "seo and digital marketing",
        ]
        ordered_phrases = sorted(
            (
                (lower_text.find(phrase), phrase)
                for phrase in known_phrases
                if phrase in lower_text
            ),
            key=lambda item: item[0],
        )
        for _, phrase in ordered_phrases:
            formatted = phrase.title().replace("Seo", "SEO")
            candidates.append(formatted)

        banned = {"Our Services", "Best Pricing", "Our Pricing", "About Us"}
        cleaned: List[str] = []
        for c in candidates:
            item = self._clean_answer_text(c).strip(". ")
            if not item or item in banned:
                continue
            if len(item.split()) > 6:
                continue
            if any(item.lower() == x.lower() for x in cleaned):
                continue
            cleaned.append(item)
        return cleaned[:10]

    def _extract_pricing_summary(self, docs: List[Document], corpus_docs: List[Document]) -> Optional[str]:
        pricing_docs = [
            doc for doc in (docs or []) + (corpus_docs or [])
            if self._page_type(doc.metadata or {}) == "pricing"
            or "pricing" in ((doc.metadata or {}).get("title") or "").lower()
            or "pricing" in ((doc.metadata or {}).get("source") or "").lower()
        ]
        if not pricing_docs:
            return None

        pricing_text = " ".join(" ".join((doc.page_content or "").split()) for doc in pricing_docs)
        pricing_lines = re.findall(
            r"([^.]{0,160}(?:pricing|starter|pro|enterprise|per month|custom|plan)[^.]{0,220}\.)",
            pricing_text,
            flags=re.IGNORECASE,
        )
        if pricing_lines:
            deduped: List[str] = []
            for line in pricing_lines:
                cleaned = self._clean_answer_text(line)
                if not cleaned:
                    continue
                if any(cleaned.lower() == existing.lower() for existing in deduped):
                    continue
                deduped.append(cleaned)
                if len(deduped) >= 3:
                    break
            if deduped:
                return "Here is the pricing information currently available: " + " ".join(deduped)
        return None

    def _is_irrelevant_tile_query(self, question: str, doc_text: str) -> bool:
        q = (question or "").lower()
        text = (doc_text or "").lower()
        asks_tiles = any(token in q for token in ("tile", "tiles", "floor tiles", "wall tiles", "bathroom tiles"))
        if not asks_tiles:
            return False

        tile_signals = (
            "tile", "tiles", "ceramic", "porcelain", "vitrified", "gvt", "bathroom tiles",
            "floor tiles", "wall tiles", "catalog", "catalogue"
        )
        service_signals = (
            "cloud", "migration", "web development", "graphic design", "server-side",
            "engineers", "infrastructure", "consultation", "our services"
        )
        has_tile_context = any(token in text for token in tile_signals)
        has_service_context = any(token in text for token in service_signals)
        return not has_tile_context and has_service_context

    def _synthesize_ledger_answer(
        self,
        question: str,
        snippets: List[str],
        bot_instructions: str = "",
        bot_name: Optional[str] = None,
    ) -> Optional[str]:
        """Use LLM to rewrite retrieved chunks into a concise support answer."""
        if not snippets:
            return None
        try:
            llm = _get_llm()
            context_text = "\n".join(snippets[:5])
            synthesis_prompt = (
                f"{self._build_behavior_prompt(bot_instructions, bot_name)}\n"
                "You must answer using ONLY the context below. "
                "Do not copy long fragments verbatim. "
                "If information is missing, say so briefly.\n\n"
                f"User question:\n{question}\n\n"
                f"Retrieved context:\n{context_text}\n\n"
                "Write a clean customer-support answer in 3-6 lines."
            )
            result = llm.invoke(synthesis_prompt)
            text = getattr(result, "content", None) if result else None
            if isinstance(text, list):
                text = " ".join(str(x) for x in text)
            if text and str(text).strip():
                return self._clean_answer_text(str(text).strip())
        except Exception:
            return None
        return None

    def query(
        self,
        question: str,
        collection_name: str = "default",
        chat_history: List = None,
        bot_instructions: str = "",
        bot_name: Optional[str] = None,
    ):
        with tracer.start_as_current_span("rag_query") as span:
            span.set_attribute("collection", collection_name)
            span.set_attribute("question_length", len(question))
            scenario = self._classify_question_scenario(question)
            span.set_attribute("scenario", scenario)

            if scenario == "neutral":
                return self._response(self._neutral_answer(question), [])
            if scenario == "negative":
                return self._response(self._negative_answer(question), [])

            start = time.perf_counter()
            vector_store = self.get_vector_store(collection_name)
            llm = _get_llm()
            retrieval_k = self._retrieval_k(question)
            fetch_k = max(retrieval_k * 3, settings.RAG_RETRIEVAL_FETCH_K)
            retrieval_strategy = "hybrid"

            history = chat_history or []
            standalone_question = question
            if history:
                history_prompt = (
                    "Given the chat history and latest user question, rewrite the latest question "
                    "so it is standalone. Return only the rewritten question.\n\n"
                    f"History:\n{self._render_history(history)}\n\n"
                    f"Latest question:\n{question}"
                )
                try:
                    reformulated = llm.invoke(history_prompt)
                    candidate = getattr(reformulated, "content", "") if reformulated else ""
                    if isinstance(candidate, list):
                        candidate = " ".join(str(x) for x in candidate)
                    if str(candidate).strip():
                        standalone_question = str(candidate).strip()
                except Exception:
                    standalone_question = question

            docs = self._retrieve_ranked_docs(vector_store, standalone_question, retrieval_k, fetch_k)

            context_blocks = []
            for doc in docs:
                meta = doc.metadata or {}
                title = meta.get("title") or meta.get("source") or "Knowledge Ledger"
                context_blocks.append(f"[{title}] {doc.page_content}")
            context_text = "\n\n".join(context_blocks)

            system_prompt = (
                self._build_behavior_prompt(bot_instructions, bot_name)
                + "\nUse the retrieved context below to answer.\n"
                + "Format rules: start with a direct answer sentence, then 2-5 concise bullet points if useful. "
                + "Do not echo context headings verbatim.\n\n"
                + f"Retrieved context:\n{context_text}\n\n"
                + f"Conversation history:\n{self._render_history(history)}\n\n"
                + f"User question:\n{question}"
            )
            result = llm.invoke(system_prompt)
            answer_text = getattr(result, "content", "") if result else ""
            if isinstance(answer_text, list):
                answer_text = " ".join(str(x) for x in answer_text)
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            sources = [doc.metadata for doc in docs]

            span.set_attribute("answer_length", len(str(answer_text)))
            span.set_attribute("source_count", len(sources))
            span.set_attribute("duration_ms", duration_ms)

            logger.info("rag_query_completed", extra={
                "collection": collection_name,
                "question_length": len(question),
                "answer_length": len(str(answer_text)),
                "source_count": len(sources),
                "retrieval_strategy": retrieval_strategy,
                "retrieval_k": retrieval_k,
                "retrieval_fetch_k": fetch_k,
                "history_length": len(history),
                "duration_ms": duration_ms,
            })

            return self._response(str(answer_text), sources)

    def _render_history(self, history: List) -> str:
        rendered: List[str] = []
        for item in history or []:
            if isinstance(item, tuple) and len(item) >= 2:
                rendered.append(f"User: {item[0]}\nAssistant: {item[1]}")
                continue
            role = getattr(item, "type", None) or getattr(item, "role", None) or item.__class__.__name__
            content = getattr(item, "content", None)
            if content:
                rendered.append(f"{role}: {content}")
        return "\n".join(rendered).strip() or "No prior history."

    def answer_from_knowledge_ledger(
        self,
        question: str,
        collection_name: str = "default",
        k: int = 5,
        bot_instructions: str = "",
        bot_name: Optional[str] = None,
    ):
        """
        LLM-free fallback answer using top vector matches from the knowledge ledger.
        Useful when model provider is unavailable or quota-limited.
        """
        vector_store = self.get_vector_store(collection_name)
        scenario = self._classify_question_scenario(question)
        if scenario == "neutral":
            return self._response(self._neutral_answer(question), [])
        if scenario == "negative":
            return self._response(self._negative_answer(question), [])
        intent = self._question_intent(question)
        corpus_docs = self._corpus_scan_docs(vector_store, intent)
        contact_facts = self._extract_contact_facts(corpus_docs) if intent == "contact" else {}
        retrieval_k = max(3, min(k, 10))
        docs: List[Document] = []
        try:
            docs = self._retrieve_ranked_docs(vector_store, question, retrieval_k, max(retrieval_k * 3, settings.RAG_RETRIEVAL_FETCH_K))
        except Exception:
            docs = vector_store.similarity_search(question, k=retrieval_k)
        if not docs:
            return self._response(
                self._support_fallback(
                    "the details for that request",
                    "Please ask in a slightly more specific way and I’ll do my best to help."
                ),
                [],
            )
        docs = self._rank_ledger_docs(question, docs)

        snippets = []
        raw_sources = []
        seen_text = set()
        combined_text_parts = []
        for doc in docs:
            text = " ".join((doc.page_content or "").split())
            if not text:
                continue
            combined_text_parts.append(text)
            clipped = text[:320]
            if clipped in seen_text:
                continue
            seen_text.add(clipped)
            snippets.append(f"- {clipped}")
            if doc.metadata:
                raw_sources.append(doc.metadata)
        sources = self._format_sources(raw_sources)

        if not snippets:
            return self._response(
                self._support_fallback(
                    "a readable answer for that request",
                    "Please try asking in a more specific way and I’ll do my best to help."
                ),
                sources,
            )

        if self._is_identity_query(question):
            demote_markers = ("cookie", "privacy", "terms", "contact", "blog", "calendly")
            identity_lines: List[str] = []
            for doc in docs:
                meta = doc.metadata or {}
                title = (meta.get("title") or "").lower()
                source = (meta.get("source") or "").lower()
                if any(marker in title or marker in source for marker in demote_markers):
                    continue
                text = " ".join((doc.page_content or "").split())
                if not text:
                    continue
                cleaned = ""
                for part in re.split(r"(?<=[.!?])\s+", text):
                    candidate = self._clean_answer_text(part)
                    if len(candidate) < 30:
                        continue
                    if any(marker in candidate.lower() for marker in demote_markers):
                        continue
                    cleaned = candidate
                    break
                if not cleaned:
                    cleaned = self._clean_answer_text(text[:320])
                if len(cleaned) < 30:
                    continue
                if any(cleaned.lower() == x.lower() for x in identity_lines):
                    continue
                identity_lines.append(cleaned)
                if len(identity_lines) >= 2:
                    break
            if identity_lines:
                return self._response(" ".join(identity_lines), sources[:5])

        question_l = question.lower()
        doc_text = " ".join(combined_text_parts)
        profile_text = " ".join(" ".join((doc.page_content or "").split()) for doc in corpus_docs) or doc_text
        tile_candidates = sorted(set(
            m.strip() for m in re.findall(
                r"\b([A-Z][A-Za-z0-9/&+\-]*(?:\s(?!Tiles\b)[A-Z][A-Za-z0-9/&+\-]*){0,2}\sTiles)\b",
                doc_text
            )
        ))
        # Keep compact and avoid footer/policy noise.
        noisy_markers = ("policy", "notice", "return", "instruction", "catalogue", "company")
        tile_candidates = [
            x for x in tile_candidates
            if len(x.split()) <= 3 and not any(m in x.lower() for m in noisy_markers)
        ][:6]

        def _extract_first(pattern: str):
            match = re.search(pattern, doc_text, flags=re.IGNORECASE)
            return match.group(0).strip() if match else None

        def _extract_profile_value(label: str) -> Optional[str]:
            next_labels = (
                "Official website", "Business category", "Brand keyword", "Validation code",
                "Support alias", "Primary knowledge domain", "Test marker", "Support contacts", "Knowledge policy",
            )
            boundary = "|".join(re.escape(item) for item in next_labels if item.lower() != label.lower())
            match = re.search(
                rf"{re.escape(label)}:\s*(.+?)(?=\s+(?:{boundary}):|\s+(?:Support contacts|Knowledge policy)\b|$)",
                profile_text,
                flags=re.IGNORECASE,
            )
            return match.group(1).strip() if match else None

        is_top_query = any(x in question_l for x in ["top selling", "best selling", "most selling"]) or (
            "top" in question_l and "tile" in question_l
        )
        if is_top_query:
            ranked_list_match = re.search(
                r"top[- ]selling[^:]{0,60}:\s*([^.]{20,500})",
                doc_text,
                flags=re.IGNORECASE,
            )
            if ranked_list_match:
                ranked_list = ranked_list_match.group(1).strip().rstrip(",;")
                answer = f"Top-selling options from indexed data are: {ranked_list}."
                return self._response(answer, sources[:5])
            if "floor" in question_l:
                material_sentence = _extract_first(
                    r"(Made from [^.]{20,220}\.)"
                )
                benefits_sentence = _extract_first(
                    r"(Floor tiles are [^.]{20,260}\.)"
                )
                parts = []
                if material_sentence:
                    parts.append(self._clean_answer_text(material_sentence))
                if benefits_sentence:
                    parts.append(self._clean_answer_text(benefits_sentence))
                if parts:
                    answer = (
                        "I could not find an explicit top-selling rank in the indexed data. "
                        + " ".join(parts)
                    )
                    return self._response(answer, sources[:5])
            if tile_candidates:
                answer = (
                    "Based on our indexed catalog, popular options include "
                    f"{', '.join(tile_candidates)}."
                )
                if any(x in question_l for x in ["bath room", "bathroom", "washroom"]):
                    bathroom_first = [x for x in tile_candidates if x.lower() == "bathroom tiles"]
                    others = [x for x in tile_candidates if x.lower() != "bathroom tiles"]
                    if bathroom_first:
                        answer = (
                            "Based on our indexed catalog, Bathroom Tiles are listed for bathroom spaces. "
                            + (
                                f"Other commonly listed categories include {', '.join(others)}. "
                                if others else ""
                            )
                            + "I could not find an explicit top-selling rank in the indexed data."
                        )
                return self._response(answer, sources[:5])
            return self._response(
                self._support_fallback(
                    "confirmed top-selling tile details",
                    "If you want exact rankings, please index the product or sales catalog pages."
                ),
                sources[:5],
            )

        validation_code = _extract_profile_value("Validation code")
        support_alias = _extract_profile_value("Support alias")
        test_marker = _extract_profile_value("Test marker")
        official_website = _extract_profile_value("Official website")
        business_category = _extract_profile_value("Business category")
        brand_keyword = _extract_profile_value("Brand keyword")
        knowledge_domain = _extract_profile_value("Primary knowledge domain")

        if "validation code" in question_l and validation_code:
            return self._response(f"The validation code is {validation_code}.", sources[:5])
        if "support alias" in question_l and support_alias:
            return self._response(f"The support alias is {support_alias}.", sources[:5])
        if "test marker" in question_l and test_marker:
            return self._response(f"The test marker is {test_marker}.", sources[:5])
        if any(x in question_l for x in ["official website", "primary website", "website"]) and official_website:
            return self._response(f"Our official website is {official_website}.", sources[:5])
        if any(x in question_l for x in ["brand keyword", "brand key"]) and brand_keyword:
            return self._response(f"The brand keyword is {brand_keyword}.", sources[:5])
        if any(x in question_l for x in ["business category", "category"]) and business_category:
            return self._response(f"The business category is {business_category}.", sources[:5])
        if any(x in question_l for x in ["primary knowledge domain", "which domain"]) and knowledge_domain:
            return self._response(f"The primary knowledge domain is {knowledge_domain}.", sources[:5])
        if "profile summary" in question_l and (business_category or brand_keyword or official_website):
            parts = []
            if business_category:
                parts.append(f"business category: {business_category}")
            if brand_keyword:
                parts.append(f"brand keyword: {brand_keyword}")
            if official_website:
                parts.append(f"website: {official_website}")
            return self._response(
                "Here is the profile summary I found: " + ", ".join(parts) + ".",
                sources[:5],
            )

        if any(x in question_l for x in ["pricing", "price", "plan", "subscription", "cost", "enterprise pricing"]):
            pricing_summary = self._extract_pricing_summary(docs, corpus_docs)
            if pricing_summary:
                return self._response(pricing_summary, sources[:5])
            return self._response(
                self._support_fallback(
                    "clear pricing details",
                    "If you need exact pricing, please index the plan or pricing page and I’ll help with that."
                ),
                sources[:5],
            )

        phone = contact_facts.get("phone") or _extract_first(r"(\+?\d[\d\-\s()]{7,}\d)")
        email = contact_facts.get("email") or _extract_first(r"([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[A-Za-z]{2,})")
        url = _extract_first(r"(https?://[^\s]+)")
        address_line = contact_facts.get("address") or _extract_first(
            r"((?:address|office|location|head office)[:\-]?\s*[^.]{12,220})"
        )
        if not address_line:
            city_match = re.search(r"\b([A-Z][A-Za-z]+,\s*India)\b", doc_text)
            if city_match:
                address_line = city_match.group(1)
        founder_name = _extract_first(
            r"(?:(?:founder|co-founder|founded by|founded\s+by|ceo|chief executive officer|owner|managed by|led by)[:\-\s]+)([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){0,3})"
        )
        if founder_name:
            founder_name = re.sub(
                r"^(founder|co-founder|founded by|ceo|chief executive officer|owner|managed by|led by)[:\-\s]+",
                "",
                founder_name,
                flags=re.IGNORECASE,
            ).strip()

        if any(x in question_l for x in ["founder", "co-founder", "ceo", "owner", "who founded", "founder name"]):
            about_docs = [
                doc for doc in corpus_docs
                if self._page_type(doc.metadata or {}) == "about"
            ]
            about_text = " ".join(" ".join((doc.page_content or "").split()) for doc in about_docs)
            about_founder_name = None
            if about_text:
                match = re.search(
                    r"(?:(?:founder|co-founder|founded by|ceo|chief executive officer|owner|managed by|led by)[:\-\s]+)([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){0,3})",
                    about_text,
                    flags=re.IGNORECASE,
                )
                if match:
                    about_founder_name = match.group(1).strip()
            if about_founder_name:
                return self._response(f"Our founder is {about_founder_name}.", sources[:5])
            return self._response(
                self._support_fallback(
                    "the founder or leadership name",
                    "If you share the company name or index the About page, I can help with that."
                ),
                sources[:5],
            )

        if any(x in question_l for x in ["phone", "contact number", "mobile", "call", "number should i call", "contact no"]):
            if phone:
                return self._response(f"Our contact number is {phone}.", sources[:5])
            return self._response(
                self._support_fallback(
                    "an official phone number",
                    "If you share your preferred region, I can help you find the right contact page."
                ),
                sources[:5],
            )

        if any(x in question_l for x in ["email", "mail id", "mail address", "contact email"]):
            if email:
                return self._response(f"Our contact email is {email}.", sources[:5])
            return self._response(
                self._support_fallback(
                    "an official contact email",
                    "If you’d like, I can guide you to the contact page."
                ),
                sources[:5],
            )

        if any(
            x in question_l
            for x in [
                "address",
                "current address",
                "office address",
                "location",
                "where are you located",
                "where is your company",
                "company location",
                "where is the company",
            ]
        ):
            if address_line:
                cleaned_address = re.sub(r"^(address|office|location|head office)[:\\-]?\\s*", "", address_line, flags=re.IGNORECASE).strip()
                return self._response(f"Our address is {cleaned_address}.", sources[:5])
            return self._response(
                self._support_fallback(
                    "an official address",
                    "If you share the company name or contact page, I can help locate it."
                ),
                sources[:5],
            )

        if any(x in question_l for x in ["api limit", "rate limit", "rpm", "requests per minute"]):
            rate_matches = re.findall(
                r"([^.]{0,120}(?:rate limit|req/min|requests per minute|rpm|starter|pro|enterprise)[^.]{0,120}\.)",
                doc_text,
                flags=re.IGNORECASE,
            )
            lines = [x.strip() for x in rate_matches]
            if lines:
                concise = " ".join(lines)[:300]
                answer = f"Based on indexed policy content, here is the rate-limit detail I found: {concise}"
                if url:
                    answer += f" You can verify on: {url}"
                return self._response(answer, sources[:5])
            return self._response(
                self._support_fallback(
                    "an official API rate-limit policy",
                    "If you share your plan name, I can help once that policy page is indexed."
                ),
                sources[:5],
            )

        if any(x in question_l for x in ["services", "service", "offerings", "solutions", "what do you provide", "offer"]):
            service_docs = [
                doc for doc in corpus_docs
                if self._page_type(doc.metadata or {}) in {"services", "about"}
            ]
            service_text = " ".join(" ".join((doc.page_content or "").split()) for doc in service_docs) or doc_text
            if doc_text and doc_text not in service_text:
                service_text = f"{service_text} {doc_text}".strip()
            service_candidates = self._extract_service_candidates(service_text)
            if len(service_candidates) < 2:
                broader_candidates = self._extract_service_candidates(doc_text)
                for candidate in broader_candidates:
                    if all(candidate.lower() != existing.lower() for existing in service_candidates):
                        service_candidates.append(candidate)
            if service_candidates:
                answer = (
                    "Here are the services currently available: "
                    + ", ".join(service_candidates)
                    + ". If you want, I can explain each service in one line."
                )
                return self._response(answer, sources[:5])
            service_profile_markers = (
                "web design", "graphic design", "web development", "cloud migration",
                "cloud architecture", "seo & digital marketing", "seo and digital marketing",
            )
            inferred_services = [marker.title().replace("Seo", "SEO") for marker in service_profile_markers if marker in service_text.lower()]
            if inferred_services:
                answer = (
                    "Here are the services currently available: "
                    + ", ".join(dict.fromkeys(inferred_services))
                    + ". If you'd like, I can explain each service briefly."
                )
                return self._response(answer, sources[:5])
            pricing_like = any(marker in doc_text.lower() for marker in ("pricing plan", "pricing plans", "per month", "contact sales"))
            if pricing_like:
                return self._response(
                    self._support_fallback(
                        "a reliable services list",
                        "The available content looks more like pricing or general marketing copy. Please index a services or solutions page for an exact answer."
                ),
                sources[:5],
            )

        if any(
            x in question_l
            for x in [
                "what does your company do",
                "tell me about your company",
                "company profile",
                "kind of company",
                "business about",
            ]
        ):
            service_docs = [
                doc for doc in corpus_docs
                if self._page_type(doc.metadata or {}) in {"services", "about"}
            ]
            profile_text = " ".join(" ".join((doc.page_content or "").split()) for doc in service_docs) or doc_text
            service_candidates = self._extract_service_candidates(profile_text)
            if service_candidates:
                answer = (
                    "We provide services such as "
                    + ", ".join(service_candidates[:6])
                    + ". If you'd like, I can also explain our company profile or contact details."
                )
                return self._response(answer, sources[:5])
            return self._response(
                self._support_fallback(
                    "a clear company profile",
                    "If you’d like, I can still help with our services, pricing, or contact details."
                ),
                sources[:5],
            )

        if self._is_irrelevant_tile_query(question, doc_text):
            return self._response(self._not_relevant_answer(), sources[:5])

        synthesized = self._synthesize_ledger_answer(
            question=question,
            snippets=[s.replace("- ", "") for s in snippets],
            bot_instructions=bot_instructions,
            bot_name=bot_name,
        )
        if synthesized:
            return self._response(synthesized, sources[:5])

        answer = self._heuristic_compose_answer(
            question=question,
            snippets=[s.replace("- ", "") for s in snippets],
        )
        return self._response(answer, sources[:5])

rag_service = RAGService()
