#!/usr/bin/env python3
"""
Elysia-WebScout Agent
External Intelligence Officer for the Elysia system.
Researches frameworks, patterns, and examples on the web,
then summarizes and distills them into designs and TODOs.

SECURITY: This module performs web research and should be used with caution.
All network operations route through WebReader gateway.
"""

import os
import json
import logging
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


try:
    from .proposal_domains import ProposalDomain, get_domain_config, validate_domain
except ImportError:
    from proposal_domains import ProposalDomain, get_domain_config, validate_domain

logger = logging.getLogger(__name__)

# Log warnings about missing dependencies (after logger is defined)
if not HAS_HTTPX:
    logger.warning("httpx not available - web reading will be limited")
if not HAS_BS4:
    logger.warning("beautifulsoup4 not available - HTML parsing will be limited")


@dataclass
class ResearchSource:
    """Represents a research source"""
    url: str
    title: str
    relevance: str  # "high", "medium", "low"
    extracted_patterns: List[str]
    summary: Optional[str] = None


@dataclass
class ProposalMetadata:
    """Proposal metadata following the schema"""
    proposal_id: str
    title: str
    description: str
    status: str  # "research", "design", "proposal", "approved", "rejected", "implemented"
    created_by: str = "elysia-webscout"
    created_at: str = None
    updated_at: str = None
    last_updated_by: Optional[str] = None
    schema_version: int = 1  # Schema version for evolution tracking
    domain: Optional[str] = None  # e.g., "elysia_core", "hestia_scraping", "legal_pipeline"
    priority: str = "medium"  # "low", "medium", "high"
    impact_score: Optional[int] = None  # 1-5 scale
    effort_score: Optional[int] = None  # 1-5 scale
    risk_level: str = "medium"  # "low", "medium", "high"
    tags: List[str] = None
    research_sources: List[Dict[str, Any]] = None
    design_impact: Dict[str, Any] = None
    approval_status: str = "pending"
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    rejection_reason: Optional[str] = None
    implementation_status: str = "not_started"
    implementation_notes: List[str] = None
    history: List[Dict[str, Any]] = None  # Audit trail

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
        if self.updated_at is None:
            self.updated_at = datetime.now().isoformat()
        if self.last_updated_by is None:
            self.last_updated_by = self.created_by
        if self.research_sources is None:
            self.research_sources = []
        if self.tags is None:
            self.tags = []
        if self.design_impact is None:
            self.design_impact = {
                "modules_affected": [],
                "complexity": "medium",
                "estimated_effort_hours": 0,
                "breaking_changes": False,
                "dependencies": []
            }
        if self.implementation_notes is None:
            self.implementation_notes = []
        if self.history is None:
            self.history = []
    
    def add_history_entry(self, actor: str, change_summary: str):
        """Add an entry to the proposal history"""
        self.history.append({
            "timestamp": datetime.now().isoformat(),
            "actor": actor,
            "change_summary": change_summary
        })
        self.updated_at = datetime.now().isoformat()
        self.last_updated_by = actor
    
    def calculate_priority_score(self) -> float:
        """Calculate priority score based on impact/effort ratio"""
        if self.impact_score is None or self.effort_score is None:
            return 0.0
        if self.effort_score == 0:
            return float('inf') if self.impact_score > 0 else 0.0
        return self.impact_score / self.effort_score


class ElysiaWebScout:
    """
    Elysia-WebScout Agent
    
    Core mission: Research frameworks, patterns, and examples on the web,
    then summarize and distill them into designs and TODOs.
    Never makes irreversible repository changes without explicit approval.
    """
    
    def __init__(self, web_reader=None, proposals_root: Optional[Path] = None, require_api_keys: bool = False):
        """
        Initialize WebScout agent.
        
        Args:
            web_reader: WebReader instance (optional - will try to get from GuardianCore singleton if None,
                unless ELYSIA_WEBSCOUT_SKIP_GUARDIAN_READER=1)
            proposals_root: Root directory for proposals (default: ./proposals)
            require_api_keys: If True, raise error if no API keys available.
                            If False, run in simulated mode.
        """
        # Agent identity (set early for logging)
        self.agent_name = "Elysia-WebScout"
        self.role = "External Intelligence Officer"
        
        # Try to get web_reader from GuardianCore singleton if not provided
        if web_reader is None and os.environ.get("ELYSIA_WEBSCOUT_SKIP_GUARDIAN_READER") != "1":
            try:
                try:
                    from .guardian_singleton import get_guardian_core
                except ImportError:
                    from guardian_singleton import get_guardian_core
                guardian_core = get_guardian_core()
                if guardian_core and hasattr(guardian_core, 'web_reader') and guardian_core.web_reader:
                    web_reader = guardian_core.web_reader
                    logger.info(f"{self.agent_name} using WebReader from GuardianCore singleton")
            except Exception as e:
                logger.warning(f"{self.agent_name} could not get WebReader from GuardianCore: {e} - URL research will be disabled")
        
        self.web_reader = web_reader
        self.proposals_root = proposals_root or Path("proposals")
        self.proposals_root.mkdir(exist_ok=True)
        
        if self.web_reader is None:
            if os.environ.get("ELYSIA_WEBSCOUT_SKIP_GUARDIAN_READER") == "1":
                logger.debug(
                    "%s: no WebReader (ELYSIA_WEBSCOUT_SKIP_GUARDIAN_READER=1); URL research disabled",
                    self.agent_name,
                )
            else:
                logger.warning(
                    "%s initialized without WebReader - URL research features will be disabled",
                    self.agent_name,
                )
        
        # Brave Search API rate limiting (2000 requests/month)
        self.brave_search_limit = 2000
        self.brave_search_usage_file = self.proposals_root.parent / "config" / "brave_search_usage.json"
        self.brave_search_usage = self._load_brave_search_usage()
        
        # Tavily API rate limiting (1000 requests/month)
        self.tavily_limit = 1000
        self.tavily_usage_file = self.proposals_root.parent / "config" / "tavily_usage.json"
        self.tavily_usage = self._load_tavily_usage()
        
        # Load API keys
        try:
            try:
                from project_guardian.api_key_manager import get_api_key_manager
            except ImportError:
                from api_key_manager import get_api_key_manager
            self.api_manager = get_api_key_manager()
            self.has_llm = self.api_manager.has_llm_access()
            
            if require_api_keys:
                self.api_manager.require_llm_access()
            
            if not self.has_llm:
                logger.warning(f"{self.agent_name} running in simulated mode (no API keys)")
            else:
                logger.info(f"{self.agent_name} initialized with LLM access")
        except ImportError:
            logger.warning("API key manager not available. Running in simulated mode.")
            self.api_manager = None
            self.has_llm = False
        except RuntimeError as e:
            if require_api_keys:
                raise
            logger.warning(f"{self.agent_name} running in simulated mode: {e}")
            self.has_llm = False
        
        logger.info(f"{self.agent_name} initialized")
    
    def _load_brave_search_usage(self) -> Dict[str, Any]:
        """Load Brave Search API usage tracking."""
        if not self.brave_search_usage_file.exists():
            return {
                "current_month": datetime.now().strftime("%Y-%m"),
                "requests_this_month": 0,
                "last_reset": datetime.now().isoformat()
            }
        
        try:
            with open(self.brave_search_usage_file, 'r', encoding='utf-8') as f:
                usage = json.load(f)
            
            # Reset if new month
            current_month = datetime.now().strftime("%Y-%m")
            if usage.get("current_month") != current_month:
                usage = {
                    "current_month": current_month,
                    "requests_this_month": 0,
                    "last_reset": datetime.now().isoformat()
                }
                self._save_brave_search_usage(usage)
            
            return usage
        except Exception as e:
            logger.warning(f"Failed to load Brave Search usage: {e}")
            return {
                "current_month": datetime.now().strftime("%Y-%m"),
                "requests_this_month": 0,
                "last_reset": datetime.now().isoformat()
            }
    
    def _save_brave_search_usage(self, usage: Optional[Dict[str, Any]] = None):
        """Save Brave Search API usage tracking."""
        if usage is None:
            usage = self.brave_search_usage
        
        try:
            self.brave_search_usage_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.brave_search_usage_file, 'w', encoding='utf-8') as f:
                json.dump(usage, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save Brave Search usage: {e}")
    
    def _check_brave_search_limit(self) -> Tuple[bool, int, int]:
        """
        Check if Brave Search API limit is available.
        
        Returns:
            (can_use, current_usage, limit)
        """
        current = self.brave_search_usage.get("requests_this_month", 0)
        limit = self.brave_search_limit
        
        # Warn at 80% and 95%
        if current >= limit * 0.95:
            logger.error(f"Brave Search API: {current}/{limit} requests used (95%+) - LIMIT REACHED")
            return False, current, limit
        elif current >= limit * 0.80:
            logger.warning(f"Brave Search API: {current}/{limit} requests used (80%+) - Approaching limit")
        
        return current < limit, current, limit
    
    def _increment_brave_search_usage(self):
        """Increment Brave Search API usage counter."""
        self.brave_search_usage["requests_this_month"] = self.brave_search_usage.get("requests_this_month", 0) + 1
        self._save_brave_search_usage()
    
    def _load_tavily_usage(self) -> Dict[str, Any]:
        """Load Tavily API usage tracking."""
        if not self.tavily_usage_file.exists():
            return {
                "current_month": datetime.now().strftime("%Y-%m"),
                "requests_this_month": 0,
                "last_reset": datetime.now().isoformat()
            }
        
        try:
            with open(self.tavily_usage_file, 'r', encoding='utf-8') as f:
                usage = json.load(f)
            
            # Reset if new month
            current_month = datetime.now().strftime("%Y-%m")
            if usage.get("current_month") != current_month:
                usage = {
                    "current_month": current_month,
                    "requests_this_month": 0,
                    "last_reset": datetime.now().isoformat()
                }
                self._save_tavily_usage(usage)
            
            return usage
        except Exception as e:
            logger.warning(f"Failed to load Tavily usage: {e}")
            return {
                "current_month": datetime.now().strftime("%Y-%m"),
                "requests_this_month": 0,
                "last_reset": datetime.now().isoformat()
            }
    
    def _save_tavily_usage(self, usage: Optional[Dict[str, Any]] = None):
        """Save Tavily API usage tracking."""
        if usage is None:
            usage = self.tavily_usage
        
        try:
            self.tavily_usage_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.tavily_usage_file, 'w', encoding='utf-8') as f:
                json.dump(usage, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save Tavily usage: {e}")
    
    def _check_tavily_limit(self) -> Tuple[bool, int, int]:
        """
        Check if Tavily API limit is available.
        
        Returns:
            (can_use, current_usage, limit)
        """
        current = self.tavily_usage.get("requests_this_month", 0)
        limit = self.tavily_limit
        
        # Warn at 80% and 95%
        if current >= limit * 0.95:
            logger.error(f"Tavily API: {current}/{limit} requests used (95%+) - LIMIT REACHED")
            return False, current, limit
        elif current >= limit * 0.80:
            logger.warning(f"Tavily API: {current}/{limit} requests used (80%+) - Approaching limit")
        
        return current < limit, current, limit
    
    def _increment_tavily_usage(self):
        """Increment Tavily API usage counter."""
        self.tavily_usage["requests_this_month"] = self.tavily_usage.get("requests_this_month", 0) + 1
        self._save_tavily_usage()
    
    def create_proposal(self, task_description: str, topic: str, domain: Optional[str] = None, 
                       tags: Optional[List[str]] = None, check_duplicates: bool = True) -> Dict[str, Any]:
        """
        Create a new proposal from a research task.
        
        Args:
            task_description: The research task description
            topic: Topic slug for the proposal (e.g., "multi-agent-orchestration")
            domain: Domain (required, must be one of ProposalDomain enum values)
            tags: Optional tags for the proposal
            check_duplicates: Whether to check for similar existing proposals
        
        Returns:
            Dict with "proposal_id" and "similar_proposals" (if duplicates found)
        
        Raises:
            ValueError: If domain is invalid or missing
        """
        title = f"Research: {topic.replace('-', ' ').title()}"
        
        # Validate domain (required and must be canonical)
        if not domain:
            # Try to infer from topic/tags, but ultimately require explicit domain
            logger.warning("Domain not specified. Proposal creation requires a canonical domain.")
            raise ValueError("Domain is required. Must be one of: " + ", ".join(ProposalDomain.values()))
        
        is_valid, error_msg = validate_domain(domain)
        if not is_valid:
            raise ValueError(error_msg)
        
        # Check for duplicates if enabled
        similar_proposals = []
        if check_duplicates:
            try:
                try:
                    from project_guardian.proposal_system import ProposalLifecycleManager
                except ImportError:
                    from proposal_system import ProposalLifecycleManager
                lifecycle_manager = ProposalLifecycleManager(self.proposals_root)
                similar_proposals = lifecycle_manager.find_similar_proposals(
                    title=title,
                    tags=tags or [],
                    domain=domain
                )
                if similar_proposals:
                    logger.warning(f"Found {len(similar_proposals)} similar proposals. Consider refining existing ones.")
            except Exception as e:
                logger.warning(f"Could not check for duplicates: {e}")
        
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        proposal_id = f"webscout-{timestamp}-{topic}"
        proposal_path = self.proposals_root / proposal_id
        proposal_path.mkdir(exist_ok=True)
        
        # Create folder structure
        (proposal_path / "research").mkdir(exist_ok=True)
        (proposal_path / "design").mkdir(exist_ok=True)
        (proposal_path / "implementation").mkdir(exist_ok=True)
        (proposal_path / "implementation" / "patches").mkdir(exist_ok=True)
        
        # Create initial metadata (domain is now validated)
        metadata = ProposalMetadata(
            proposal_id=proposal_id,
            title=title,
            description=task_description,
            status="research",
            domain=domain,  # Now guaranteed to be valid
            tags=tags or [],
            schema_version=1
        )
        
        # Add initial history entry
        metadata.add_history_entry(
            actor="elysia-webscout",
            change_summary="Proposal created"
        )
        
        # Save metadata
        metadata_path = proposal_path / "metadata.json"
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(asdict(metadata), f, indent=2, ensure_ascii=False)
        
        # Create README
        readme_path = proposal_path / "README.md"
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(f"# {metadata.title}\n\n")
            f.write(f"**Proposal ID**: {proposal_id}\n")
            f.write(f"**Status**: {metadata.status}\n")
            f.write(f"**Created**: {metadata.created_at}\n")
            if domain:
                f.write(f"**Domain**: {domain}\n")
            if tags:
                f.write(f"**Tags**: {', '.join(tags)}\n")
            f.write(f"\n## Task Description\n\n{task_description}\n\n")
            f.write("## Status\n\nThis proposal is in the research phase.\n")
        
        logger.info(f"Created proposal: {proposal_id}")
        
        return {
            "proposal_id": proposal_id,
            "similar_proposals": similar_proposals
        }
    
    def conduct_web_research(self, query: str, max_sources: int = 5) -> Tuple[List[ResearchSource], str]:
        """
        Conduct web research on a query.
        
        Uses LLM API if available, otherwise runs in simulated mode.
        
        Args:
            query: Research query
            max_sources: Maximum number of sources to return
        
        Returns:
            Tuple of (sources, summary)
        """
        if not self.has_llm or not self.api_manager:
            # Simulated research mode
            logger.info(f"Running simulated research for: {query}")
            return self._simulated_research(query, max_sources)
        
        # Real research using LLM
        try:
            return self._llm_research(query, max_sources)
        except Exception as e:
            logger.warning(f"LLM research failed, falling back to simulated: {e}")
            return self._simulated_research(query, max_sources)
    
    def _simulated_research(self, query: str, max_sources: int) -> Tuple[List[ResearchSource], str]:
        """Generate simulated research results"""
        sources = [
            ResearchSource(
                url=f"https://example.com/research/{query.replace(' ', '-').lower()}-{i}",
                title=f"Simulated Source {i+1} for {query}",
                relevance="high" if i < 2 else "medium",
                extracted_patterns=[
                    f"Pattern {i+1}-A: Description of pattern",
                    f"Pattern {i+1}-B: Another pattern"
                ],
                summary=f"Simulated summary for source {i+1} on {query}"
            )
            for i in range(min(max_sources, 3))
        ]
        
        summary = f"## Research Summary for '{query}'\n\n"
        summary += "**Note**: This is simulated research. Real API keys are required for actual web research.\n\n"
        summary += f"### Key Findings:\n"
        summary += f"- Found {len(sources)} relevant sources\n"
        summary += f"- Extracted {sum(len(s.extracted_patterns) for s in sources)} patterns\n"
        summary += f"- Research topic: {query}\n\n"
        summary += "### Next Steps:\n"
        summary += "- Configure API keys for real web research\n"
        summary += "- Review extracted patterns\n"
        summary += "- Integrate findings into proposal design\n"
        
        return sources, summary
    
    def _llm_research(self, query: str, max_sources: int) -> Tuple[List[ResearchSource], str]:
        """
        Conduct research using LLM API + actual web reading.
        
        Process:
        1. Use LLM to generate search queries and suggest URLs
        2. Actually fetch and read web pages
        3. Extract and summarize findings
        4. Return structured sources with real content
        """
        client = self.api_manager.get_llm_client()
        if not client:
            raise RuntimeError("No LLM client available")
        
        try:
            from .prompts.prompt_builder import log_legacy_llm_call

            log_legacy_llm_call(
                "",
                caller="WebScoutAgent.research_with_llm",
                reason="inline_prompt_webscout_research",
            )
            # Step 1: Use LLM to generate search queries and suggest URLs
            if hasattr(client, 'chat'):  # OpenAI-style
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a research assistant. For the given query, suggest 3-5 specific URLs that would contain relevant information. Return only a JSON array of URLs, like: [\"https://example.com/page1\", \"https://example.com/page2\"]"},
                        {"role": "user", "content": f"Research query: {query}\n\nSuggest {max_sources} specific URLs that would help answer this query. Return only a JSON array of URLs."}
                    ],
                    temperature=0.3,
                    max_tokens=500
                )
                llm_response = response.choices[0].message.content
                
                # Extract URLs from LLM response
                urls = self._extract_urls_from_llm_response(llm_response)
                
                # If LLM didn't provide URLs, use a web search approach
                if not urls:
                    logger.warning("LLM didn't provide URLs, using fallback search")
                    urls = self._generate_search_urls(query, max_sources)
            else:
                # Fallback: generate search URLs
                urls = self._generate_search_urls(query, max_sources)
            
            # Step 2: Actually fetch and read web pages
            sources = []
            for url in urls[:max_sources]:
                try:
                    source = self._fetch_and_parse_webpage(url, query)
                    if source:
                        sources.append(source)
                except Exception as e:
                    logger.warning(f"Failed to fetch {url}: {e}")
                    continue
            
            # If we couldn't fetch any pages, fall back to LLM-only research
            if not sources:
                logger.warning("No web pages fetched, falling back to LLM-only research")
                return self._llm_only_research(query, max_sources)
            
            # Step 3: Use LLM to summarize findings
            sources_text = "\n\n".join([
                f"Source {i+1}: {s.title}\nURL: {s.url}\nSummary: {s.summary}\nPatterns: {', '.join(s.extracted_patterns)}"
                for i, s in enumerate(sources)
            ])
            
            if hasattr(client, 'chat'):
                summary_response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a research assistant. Summarize the research findings from the provided sources."},
                        {"role": "user", "content": f"Research query: {query}\n\nSources found:\n{sources_text}\n\nProvide a comprehensive research summary."}
                    ],
                    temperature=0.7,
                    max_tokens=1500
                )
                research_summary = summary_response.choices[0].message.content
            else:
                research_summary = f"## Research Summary for '{query}'\n\nFound {len(sources)} sources with relevant information."
            
            return sources, research_summary
            
        except Exception as e:
            logger.error(f"LLM research error: {e}")
            # Fallback to LLM-only research
            return self._llm_only_research(query, max_sources)
    
    def _extract_urls_from_llm_response(self, text: str) -> List[str]:
        """Extract URLs from LLM response text."""
        urls = []
        
        # Try to parse as JSON array
        try:
            import json
            # Find JSON array in response
            json_match = re.search(r'\[.*?\]', text, re.DOTALL)
            if json_match:
                urls = json.loads(json_match.group())
        except (json.JSONDecodeError, AttributeError, ValueError):
            # JSON parsing failed or match group issue - skip
            pass
        
        # Also extract URLs using regex
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        found_urls = re.findall(url_pattern, text)
        urls.extend(found_urls)
        
        # Remove duplicates and validate
        urls = list(set(urls))
        urls = [u for u in urls if u.startswith(('http://', 'https://'))]
        
        return urls[:10]  # Limit to 10 URLs
    
    def _generate_search_urls(self, query: str, max_sources: int) -> List[str]:
        """
        Generate search URLs using Tavily or Brave Search API.
        
        Tries Tavily first (better for research), then falls back to Brave Search.
        
        Returns list of URLs from search results.
        """
        if not self.api_manager:
            logger.debug("API manager not available, cannot generate search URLs")
            return []
        
        # Try Tavily first (better for research, provides summaries)
        if self.api_manager.keys.tavily:
            try:
                urls = self._tavily_search(query, max_sources)
                if urls:
                    return urls
            except Exception as e:
                logger.warning(f"Tavily search failed: {e}")
        
        # Fall back to Brave Search
        if self.api_manager.keys.brave_search:
            try:
                return self._brave_search(query, max_sources)
            except Exception as e:
                logger.warning(f"Brave Search failed: {e}")
        
        logger.debug("No search API keys available, cannot generate search URLs")
        return []
    
    def _brave_search(self, query: str, count: int = 10) -> List[str]:
        """
        Search using Brave Search API with rate limiting.
        
        Args:
            query: Search query
            count: Number of results to return (max 20)
        
        Returns:
            List of URLs from search results
        """
        if not HAS_HTTPX:
            logger.warning("httpx not available for Brave Search")
            return []
        
        api_key = self.api_manager.keys.brave_search
        if not api_key:
            return []
        
        # Check rate limit
        can_use, current, limit = self._check_brave_search_limit()
        if not can_use:
            logger.error(f"Brave Search API limit reached ({current}/{limit}). Cannot perform search.")
            return []
        
        try:
            # Brave Search API endpoint
            url = "https://api.search.brave.com/res/v1/web/search"
            
            params = {
                "q": query,
                "count": min(count, 20),  # Brave API max is 20
                "search_lang": "en",
                "country": "US",
                "safesearch": "moderate",
            }
            
            headers = {
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": api_key,
            }
            
            # Route through WebReader gateway
            if not self.web_reader:
                logger.warning("Brave Search requires WebReader (not available)")
                return []
            
            # Note: urllib.request doesn't support params directly, so we append to URL
            url_with_params = f"{url}?{'&'.join(f'{k}={v}' for k, v in params.items())}"
            response = self.web_reader.request_json(
                method="GET",
                url=url_with_params,
                headers=headers,
                timeout_s=10,
                caller_identity=self.agent_name,
                task_id=None
            )
            
            if response.get("status_code") != 200:
                raise Exception(f"Brave Search API returned {response.get('status_code')}")
            
            data = response.get("json") or {}
            
            # Extract URLs from search results
            urls = []
            if "web" in data and "results" in data["web"]:
                for result in data["web"]["results"]:
                    if "url" in result:
                        urls.append(result["url"])
            
            # Increment usage counter only on success
            self._increment_brave_search_usage()
            
            logger.info(f"Brave Search found {len(urls)} URLs for query: {query} (Usage: {self.brave_search_usage['requests_this_month']}/{limit})")
            return urls[:count]
            
        except Exception as e:
            logger.error(f"Brave Search API error: {e}")
            # Don't increment on error (might be rate limit or other issue)
            return []
    
    def _tavily_search(self, query: str, count: int = 10) -> List[str]:
        """
        Search using Tavily API (better for research - provides summaries).
        
        Args:
            query: Search query
            count: Number of results to return
        
        Returns:
            List of URLs from search results
        """
        if not HAS_HTTPX:
            logger.warning("httpx not available for Tavily Search")
            return []
        
        api_key = self.api_manager.keys.tavily
        if not api_key:
            return []
        
        # Check rate limit
        can_use, current, limit = self._check_tavily_limit()
        if not can_use:
            logger.error(f"Tavily API limit reached ({current}/{limit}). Cannot perform search.")
            return []
        
        try:
            # Tavily Search API endpoint
            url = "https://api.tavily.com/search"
            
            payload = {
                "api_key": api_key,
                "query": query,
                "search_depth": "basic",  # "basic" or "advanced"
                "max_results": min(count, 10),  # Tavily max is typically 10
                "include_answer": False,
                "include_raw_content": False,
                "include_domains": [],
                "exclude_domains": []
            }
            
            headers = {
                "Content-Type": "application/json"
            }
            
            # Route through WebReader gateway
            if not self.web_reader:
                logger.warning("Tavily Search requires WebReader (not available)")
                return []
            
            response = self.web_reader.request_json(
                method="POST",
                url=url,
                json_body=payload,
                headers=headers,
                timeout_s=15,
                caller_identity=self.agent_name,
                task_id=None
            )
            
            if response.get("status_code") not in (200, 201):
                raise Exception(f"Tavily API returned {response.get('status_code')}")
            
            data = response.get("json") or {}
            
            # Extract URLs from search results
            urls = []
            if "results" in data:
                for result in data["results"]:
                    if "url" in result:
                        urls.append(result["url"])
            
            # Increment usage counter only on success
            self._increment_tavily_usage()
            
            logger.info(f"Tavily Search found {len(urls)} URLs for query: {query} (Usage: {self.tavily_usage['requests_this_month']}/{limit})")
            return urls[:count]
            
        except Exception as e:
            logger.error(f"Tavily Search API error: {e}")
            # Don't increment on error
            return []
    
    def get_brave_search_usage(self) -> Dict[str, Any]:
        """
        Get current Brave Search API usage statistics.
        
        Returns:
            Dict with usage info
        """
        can_use, current, limit = self._check_brave_search_limit()
        percentage = (current / limit * 100) if limit > 0 else 0
        
        return {
            "current_month": self.brave_search_usage.get("current_month"),
            "requests_used": current,
            "requests_limit": limit,
            "requests_remaining": max(0, limit - current),
            "percentage_used": round(percentage, 1),
            "can_use": can_use,
            "last_reset": self.brave_search_usage.get("last_reset")
        }
    
    def get_tavily_usage(self) -> Dict[str, Any]:
        """
        Get current Tavily API usage statistics.
        
        Returns:
            Dict with usage info
        """
        can_use, current, limit = self._check_tavily_limit()
        percentage = (current / limit * 100) if limit > 0 else 0
        
        return {
            "current_month": self.tavily_usage.get("current_month"),
            "requests_used": current,
            "requests_limit": limit,
            "requests_remaining": max(0, limit - current),
            "percentage_used": round(percentage, 1),
            "can_use": can_use,
            "last_reset": self.tavily_usage.get("last_reset")
        }
    
    def _fetch_and_parse_webpage(self, url: str, query: str) -> Optional[ResearchSource]:
        """
        Actually fetch and parse a webpage.
        
        Returns a ResearchSource with real content, or None if fetch fails.
        """
        if not self.web_reader:
            logger.warning(f"Cannot fetch {url}: WebReader not available")
            return None
        
        try:
            # Route through WebReader gateway
            html_content = self.web_reader.fetch(
                url=url,
                max_length=10000,  # Allow larger content for research
                caller_identity=self.agent_name,
                task_id=None
            )
            
            if html_content is None:
                logger.warning(f"Failed to fetch {url}: WebReader returned None")
                return None
        except Exception as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            return None
        
        # Parse HTML
        title = url
        text_content = html_content  # WebReader.fetch already extracts text
        patterns = []
        
        try:
            from bs4 import BeautifulSoup
            HAS_BS4 = True
        except ImportError:
            HAS_BS4 = False
        
        if HAS_BS4:
            try:
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Extract title
                title_tag = soup.find('title')
                if title_tag:
                    title = title_tag.get_text().strip()
                
                # Remove script and style elements
                for script in soup(["script", "style", "nav", "footer", "header"]):
                    script.decompose()
                
                # Extract main content
                main_content = soup.find('main') or soup.find('article') or soup.find('body')
                if main_content:
                    text_content = main_content.get_text(separator=' ', strip=True)
                else:
                    text_content = soup.get_text(separator=' ', strip=True)
                
                # Extract key patterns (headings, links, etc.)
                headings = soup.find_all(['h1', 'h2', 'h3'])
                for heading in headings[:5]:
                    heading_text = heading.get_text().strip()
                    if heading_text and len(heading_text) < 100:
                        patterns.append(heading_text)
                
            except Exception as e:
                logger.warning(f"Failed to parse HTML from {url}: {e}")
                text_content = html_content[:5000]  # Fallback: use raw HTML
        else:
            # Fallback: extract text using regex
            text_content = re.sub(r'<[^>]+>', '', html_content)[:5000]
        
        # Clean up text
        text_content = re.sub(r'\s+', ' ', text_content).strip()
        
        # Create summary (first 500 chars)
        summary = text_content[:500] + "..." if len(text_content) > 500 else text_content
        
        # Determine relevance based on query keywords
        query_lower = query.lower()
        text_lower = text_content.lower()
        relevance = "high" if any(word in text_lower for word in query_lower.split()) else "medium"
        
        return ResearchSource(
            url=url,
            title=title,
            relevance=relevance,
            extracted_patterns=patterns[:5] if patterns else [f"Content from {url}"],
            summary=summary
        )
    
    def _llm_only_research(self, query: str, max_sources: int) -> Tuple[List[ResearchSource], str]:
        """Fallback: LLM-only research when web fetching fails."""
        client = self.api_manager.get_llm_client()
        if not client:
            raise RuntimeError("No LLM client available")
        
        try:
            if hasattr(client, 'chat'):  # OpenAI-style
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a research assistant. Generate a research summary and suggest relevant sources for the given query."},
                        {"role": "user", "content": f"Research query: {query}\n\nGenerate a research summary and suggest 3-5 relevant sources with URLs, titles, and key patterns."}
                    ],
                    temperature=0.7,
                    max_tokens=1000
                )
                llm_summary = response.choices[0].message.content
            else:
                llm_summary = f"Research summary for {query} (LLM response format not implemented)"
            
            # Parse LLM response into sources
            sources = [
                ResearchSource(
                    url=f"https://example.com/source-{i}",
                    title=f"Source {i+1} from LLM research",
                    relevance="high",
                    extracted_patterns=[f"Pattern from LLM research"],
                    summary=llm_summary[:200] + "..." if len(llm_summary) > 200 else llm_summary
                )
                for i in range(min(max_sources, 3))
            ]
            
            return sources, llm_summary
        except Exception as e:
            logger.error(f"LLM-only research error: {e}")
            raise
    
    def add_research(self, proposal_id: str, sources: List[ResearchSource], summary: str):
        """
        Add research findings to a proposal.
        
        Args:
            proposal_id: The proposal ID
            sources: List of research sources
            summary: Research summary
        """
        proposal_path = self.proposals_root / proposal_id
        if not proposal_path.exists():
            raise ValueError(f"Proposal {proposal_id} not found")
        
        # Save research summary
        summary_path = proposal_path / "research" / "summary.md"
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write(f"# Research Summary\n\n")
            f.write(f"**Proposal**: {proposal_id}\n")
            f.write(f"**Date**: {datetime.now().isoformat()}\n\n")
            f.write(summary)
        
        # Save sources
        sources_data = []
        sources_md = []
        for source in sources:
            sources_data.append({
                "url": source.url,
                "title": source.title,
                "relevance": source.relevance,
                "extracted_patterns": source.extracted_patterns,
                "summary": source.summary
            })
            sources_md.append(f"### {source.title}\n")
            sources_md.append(f"**URL**: {source.url}\n")
            sources_md.append(f"**Relevance**: {source.relevance}\n")
            if source.summary:
                sources_md.append(f"**Summary**: {source.summary}\n")
            sources_md.append(f"**Extracted Patterns**:\n")
            for pattern in source.extracted_patterns:
                sources_md.append(f"- {pattern}\n")
            sources_md.append("\n")
        
        sources_path = proposal_path / "research" / "sources.md"
        with open(sources_path, 'w', encoding='utf-8') as f:
            f.write("# Research Sources\n\n")
            f.write("".join(sources_md))
        
        # Extract patterns
        all_patterns = []
        for source in sources:
            all_patterns.extend(source.extracted_patterns)
        
        patterns_path = proposal_path / "research" / "patterns.md"
        with open(patterns_path, 'w', encoding='utf-8') as f:
            f.write("# Extracted Patterns\n\n")
            for i, pattern in enumerate(all_patterns, 1):
                f.write(f"{i}. {pattern}\n")
        
        # Update metadata
        self._update_metadata(proposal_id, {
            "research_sources": sources_data,
            "status": "research",
            "updated_at": datetime.now().isoformat()
        })
        
        logger.info(f"Added research to proposal {proposal_id}: {len(sources)} sources")
    
    def add_design(self, proposal_id: str, architecture: str, integration: str, api_spec: Optional[str] = None):
        """
        Add design documents to a proposal.
        
        Args:
            proposal_id: The proposal ID
            architecture: Architecture design document
            integration: Integration points document
            api_spec: Optional API specification
        """
        proposal_path = self.proposals_root / proposal_id
        if not proposal_path.exists():
            raise ValueError(f"Proposal {proposal_id} not found")
        
        # Save architecture
        arch_path = proposal_path / "design" / "architecture.md"
        with open(arch_path, 'w', encoding='utf-8') as f:
            f.write(architecture)
        
        # Save integration
        int_path = proposal_path / "design" / "integration.md"
        with open(int_path, 'w', encoding='utf-8') as f:
            f.write(integration)
        
        # Save API spec if provided
        if api_spec:
            api_path = proposal_path / "design" / "api.md"
            with open(api_path, 'w', encoding='utf-8') as f:
                f.write(api_spec)
        
        # Update metadata
        self._update_metadata(proposal_id, {
            "status": "design",
            "updated_at": datetime.now().isoformat()
        })
        
        logger.info(f"Added design to proposal {proposal_id}")
    
    def add_implementation(self, proposal_id: str, todos: List[Dict[str, Any]], patches: Optional[List[str]] = None, tests: Optional[str] = None):
        """
        Add implementation plan to a proposal.
        
        Args:
            proposal_id: The proposal ID
            todos: List of TODO items with priorities
            patches: Optional list of patch file paths
            tests: Optional test requirements document
        """
        proposal_path = self.proposals_root / proposal_id
        if not proposal_path.exists():
            raise ValueError(f"Proposal {proposal_id} not found")
        
        # Save TODOs
        todos_path = proposal_path / "implementation" / "todos.md"
        with open(todos_path, 'w', encoding='utf-8') as f:
            f.write("# Implementation TODOs\n\n")
            f.write("## Priority Order\n\n")
            for i, todo in enumerate(todos, 1):
                priority = todo.get("priority", "medium")
                f.write(f"{i}. **[{priority.upper()}]** {todo.get('task', 'Unknown task')}\n")
                if todo.get("notes"):
                    f.write(f"   - {todo['notes']}\n")
                f.write("\n")
        
        # Save patches if provided
        if patches:
            patches_dir = proposal_path / "implementation" / "patches"
            for i, patch_content in enumerate(patches, 1):
                patch_path = patches_dir / f"patch_{i:03d}.patch"
                with open(patch_path, 'w', encoding='utf-8') as f:
                    f.write(patch_content)
        
        # Save tests if provided
        if tests:
            tests_path = proposal_path / "implementation" / "tests.md"
            with open(tests_path, 'w', encoding='utf-8') as f:
                f.write(tests)
        
        # Update metadata
        self._update_metadata(proposal_id, {
            "status": "proposal",
            "updated_at": datetime.now().isoformat()
        })
        
        logger.info(f"Added implementation plan to proposal {proposal_id}")
    
    def _update_metadata(self, proposal_id: str, updates: Dict[str, Any], actor: str = "elysia-webscout", 
                        change_summary: str = "Metadata updated"):
        """Update proposal metadata with history tracking"""
        proposal_path = self.proposals_root / proposal_id
        metadata_path = proposal_path / "metadata.json"
        
        if metadata_path.exists():
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata_dict = json.load(f)
            
            # Load into ProposalMetadata for history tracking
            metadata = ProposalMetadata(**metadata_dict)
            
            # Update fields
            for key, value in updates.items():
                if hasattr(metadata, key):
                    setattr(metadata, key, value)
            
            # Add history entry
            metadata.add_history_entry(actor, change_summary)
            
            # Save updated metadata
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(asdict(metadata), f, indent=2, ensure_ascii=False)
        else:
            raise ValueError(f"Metadata not found for proposal {proposal_id}")
    
    def get_proposal(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        """Get proposal data"""
        proposal_path = self.proposals_root / proposal_id
        if not proposal_path.exists():
            return None
        
        metadata_path = proposal_path / "metadata.json"
        if metadata_path.exists():
            with open(metadata_path, 'r') as f:
                return json.load(f)
        return None
    
    def list_proposals(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all proposals, optionally filtered by status"""
        proposals = []
        for proposal_dir in self.proposals_root.iterdir():
            if proposal_dir.is_dir():
                metadata_path = proposal_dir / "metadata.json"
                if metadata_path.exists():
                    with open(metadata_path, 'r') as f:
                        metadata = json.load(f)
                    if status_filter is None or metadata.get("status") == status_filter:
                        proposals.append(metadata)
        return sorted(proposals, key=lambda x: x.get("created_at", ""), reverse=True)


# Example usage
if __name__ == "__main__":
    scout = ElysiaWebScout()
    
    # Create a proposal
    proposal_id = scout.create_proposal(
        task_description="Survey LangGraph, AutoGen, CrewAI for multi-agent orchestration patterns",
        topic="multi-agent-orchestration"
    )
    
    print(f"Created proposal: {proposal_id}")
    
    # Add research (example)
    sources = [
        ResearchSource(
            url="https://langchain-ai.github.io/langgraph/",
            title="LangGraph Documentation",
            relevance="high",
            extracted_patterns=["Task graphs", "State management", "Human-in-the-loop"],
            summary="LangGraph provides task graph orchestration for multi-agent systems"
        )
    ]
    
    scout.add_research(
        proposal_id,
        sources,
        "Research summary of multi-agent frameworks..."
    )
    
    print(f"Added research to {proposal_id}")

