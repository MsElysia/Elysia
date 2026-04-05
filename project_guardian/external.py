# project_guardian/external.py
# External Interaction Systems for Project Guardian

import requests
import threading
import pyttsx3
import json
import urllib.request
import urllib.parse
import urllib.error
import ipaddress
from typing import Dict, Any, List, Optional, Literal, Tuple
from urllib.parse import urlparse
from .memory import MemoryCore
from .trust import NETWORK_ACCESS


class TrustDeniedError(Exception):
    """Exception raised when TrustMatrix denies an action."""
    def __init__(self, component: str, action: str, target: str, reason: str, context: Optional[Dict[str, Any]] = None):
        self.component = component
        self.action = action
        self.target = target
        self.reason = reason
        self.context = context or {}
        message = f"Trust denied: {component} cannot perform {action} on {target}. Reason: {reason}"
        super().__init__(message)


class TrustReviewRequiredError(Exception):
    """Exception raised when TrustMatrix requires review before action."""
    def __init__(self, request_id: str, component: str, action: str, target: str, summary: str, context: Optional[Dict[str, Any]] = None):
        self.request_id = request_id
        self.component = component
        self.action = action
        self.target = target
        self.summary = summary
        self.context = context or {}
        message = f"Review required: {component} cannot perform {action} on {target} without approval. Request ID: {request_id}. Summary: {summary}"
        super().__init__(message)

# Optional OpenAI import
try:
    import openai
except ImportError:
    openai = None

class WebReader:
    """
    External information gathering for Project Guardian.
    Provides web scraping and content extraction capabilities.
    """
    
    def __init__(self, memory: MemoryCore, trust_matrix=None, review_queue=None, approval_store=None):
        self.memory = memory
        self.trust_matrix = trust_matrix  # TrustMatrix instance for gating
        self.review_queue = review_queue  # ReviewQueue instance
        self.approval_store = approval_store  # ApprovalStore instance
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        })
    
    def _validate_url_scheme(self, url: str) -> Tuple[str, str]:
        """
        Validate URL scheme (must be http or https).
        
        Args:
            url: URL to validate
            
        Returns:
            Tuple of (scheme, host)
            
        Raises:
            TrustDeniedError: If scheme is not http/https
        """
        try:
            parsed = urlparse(url)
            scheme = parsed.scheme.lower()
            host = parsed.netloc or ""
            
            if not scheme or scheme not in ("http", "https"):
                raise TrustDeniedError(
                    component="WebReader",
                    action=NETWORK_ACCESS,
                    target=host or url,
                    reason="UNSUPPORTED_URL_SCHEME",
                    context={"scheme": scheme or "missing", "url": url}
                )
            
            return scheme, host
        except TrustDeniedError:
            raise
        except Exception as e:
            raise TrustDeniedError(
                component="WebReader",
                action=NETWORK_ACCESS,
                target=url,
                reason="UNSUPPORTED_URL_SCHEME",
                context={"error": str(e), "url": url}
            )
    
    def _is_internal_target(self, host: str) -> Tuple[bool, Optional[str]]:
        """
        Check if host is an internal target (loopback, private, link-local).
        
        Args:
            host: Hostname or IP address
            
        Returns:
            Tuple of (is_internal, blocked_reason)
            blocked_reason is None if not blocked, or reason code if blocked
        """
        if not host:
            return True, "TARGET_BLOCKED_INTERNAL"
        
        host_lower = host.lower()
        
        # Check hostname patterns
        if host_lower == "localhost":
            return True, "TARGET_BLOCKED_INTERNAL"
        if host_lower.endswith(".local"):
            return True, "TARGET_BLOCKED_INTERNAL"
        
        # Try to parse as IP address
        try:
            ip = ipaddress.ip_address(host)
            
            # Loopback
            if ip.is_loopback:
                return True, "TARGET_BLOCKED_INTERNAL"
            
            # Link-local (includes cloud metadata 169.254.169.254)
            if ip.is_link_local:
                return True, "TARGET_BLOCKED_INTERNAL"
            
            # Private (RFC1918)
            if ip.is_private:
                return True, "TARGET_BLOCKED_INTERNAL"
            
            # IPv6 ULA (fc00::/7)
            if isinstance(ip, ipaddress.IPv6Address):
                # Check for ULA (fc00::/7) and link-local (fe80::/10)
                if (ipaddress.IPv6Address('fc00::') <= ip <= ipaddress.IPv6Address('fdff:ffff:ffff:ffff:ffff:ffff:ffff:ffff')):
                    return True, "TARGET_BLOCKED_INTERNAL"
                if (ipaddress.IPv6Address('fe80::') <= ip <= ipaddress.IPv6Address('febf:ffff:ffff:ffff:ffff:ffff:ffff:ffff')):
                    return True, "TARGET_BLOCKED_INTERNAL"
            
            # Not internal
            return False, None
            
        except ValueError:
            # Not a valid IP address, treat as hostname
            # Already checked hostname patterns above
            # If we get here, it's a hostname that passed the checks
            return False, None
    
    def _validate_target(self, url: str, allow_internal: bool = False) -> Tuple[str, str, Optional[str]]:
        """
        Validate URL target (scheme + internal target check).
        
        Args:
            url: URL to validate
            allow_internal: If True, allow internal targets (but still requires TrustMatrix review/approval)
            
        Returns:
            Tuple of (scheme, host, blocked_reason)
            blocked_reason is None if not blocked, or reason code if blocked
            
        Raises:
            TrustDeniedError: If scheme invalid or internal target blocked (when allow_internal=False)
        """
        # Validate scheme
        scheme, host = self._validate_url_scheme(url)
        
        # Check if internal target
        is_internal, blocked_reason = self._is_internal_target(host)
        
        if is_internal and not allow_internal:
            # Blocked by default
            raise TrustDeniedError(
                component="WebReader",
                action=NETWORK_ACCESS,
                target=host,
                reason=blocked_reason or "TARGET_BLOCKED_INTERNAL",
                context={"scheme": scheme, "url": url, "allow_internal": False}
            )
        
        return scheme, host, blocked_reason if is_internal else None
        
    def fetch(self, url: str, max_length: int = 1000, caller_identity: Optional[str] = None, task_id: Optional[str] = None, request_id: Optional[str] = None, allow_internal: bool = False) -> Optional[str]:
        """
        Fetch content from a URL.
        
        Args:
            url: URL to fetch
            max_length: Maximum content length to return
            caller_identity: Identity of the caller (for audit)
            task_id: Task ID if available (for audit)
            request_id: Optional request ID for approval replay
            allow_internal: If True, allow internal targets (requires TrustMatrix review/approval)
            
        Returns:
            Extracted text content or None if failed (network errors, empty response)
            
        Raises:
            TrustDeniedError: If TrustMatrix denies the network fetch or target is blocked
        """
        # SSRF SAFETY FLOOR: Validate scheme and target before TrustMatrix gating
        try:
            scheme, host, blocked_reason = self._validate_target(url, allow_internal=allow_internal)
        except TrustDeniedError:
            raise  # Re-raise validation errors
        
        # GOVERNANCE GATE: TrustMatrix must approve network fetch
        if self.trust_matrix is None:
            raise TrustDeniedError(
                component="WebReader",
                action=NETWORK_ACCESS,
                target=host or url,
                reason="TrustMatrix not available",
                context={"caller": caller_identity or "unknown", "task_id": task_id or "unknown", "scheme": scheme, "allow_internal": allow_internal}
            )
        
        # Build context for trust gate (no sensitive content)
        gate_context = {
            "component": "WebReader",
            "action": NETWORK_ACCESS,
            "target": host,  # Use host, not full URL
            "scheme": scheme,
            "method": "GET",
            "allow_internal": allow_internal,
            "caller_identity": caller_identity or "unknown",
            "task_id": task_id or "unknown"
        }
        
        # Add blocked_reason if applicable
        if blocked_reason:
            gate_context["blocked_reason"] = blocked_reason
        
        # Check for replay: if request_id provided and approved, bypass review
        approved_replay = False
        if request_id and self.approval_store:
            if self.approval_store.is_approved(request_id, context=gate_context):
                # Approved request with matching context - proceed (skip gate check)
                self.memory.remember(
                    f"[WebReader] Using approved request {request_id} for {domain}",
                    category="governance",
                    priority=0.7
                )
                approved_replay = True
                # Proceed directly to network request (skip gate check below)
            else:
                # Request ID provided but not approved or context mismatch
                raise TrustDeniedError(
                    component="WebReader",
                    action=NETWORK_ACCESS,
                    target=domain,
                    reason="APPROVAL_NOT_FOUND_OR_CONTEXT_MISMATCH",
                    context=gate_context
                )
        
        # Normal gate check (only if no approved request_id)
        if not approved_replay:
            component_name = "WebReader"
            
            # For internal targets with allow_internal=True, require review/approval
            # Even if TrustMatrix would auto-allow, internal targets need explicit review
            if blocked_reason and allow_internal:
                # Force review flow for internal targets
                decision = self.trust_matrix.validate_trust_for_action(component_name, NETWORK_ACCESS, context=gate_context)
                
                # Internal targets cannot be auto-allowed - require review or explicit approval
                if decision.decision == "allow":
                    # Even if TrustMatrix allows, log that this is an internal target override
                    self.memory.remember(
                        f"[WebReader] Internal target override approved: {host} (trust: {decision.risk_score:.2f})",
                        category="governance",
                        priority=0.8
                    )
                    # Proceed with allow
                elif decision.decision == "review":
                    # Enqueue review request
                    if self.review_queue:
                        review_request_id = self.review_queue.enqueue(
                            component=component_name,
                            action=NETWORK_ACCESS,
                            context=gate_context
                        )
                        
                        summary = f"Internal target {host} requires review (trust: {decision.risk_score:.2f})"
                        error_msg = f"[WebReader] Review request created: {review_request_id} - {summary}"
                        self.memory.remember(error_msg, category="governance", priority=0.8)
                        
                        raise TrustReviewRequiredError(
                            request_id=review_request_id,
                            component=component_name,
                            action=NETWORK_ACCESS,
                            target=host,
                            summary=summary,
                            context={**gate_context, "risk_score": decision.risk_score}
                        )
                    else:
                        # No review queue - treat as deny
                        raise TrustDeniedError(
                            component=component_name,
                            action=NETWORK_ACCESS,
                            target=host,
                            reason=decision.reason_code,
                            context={**gate_context, "risk_score": decision.risk_score}
                        )
                else:  # deny
                    # Trust gate denied - raise explicit exception
                    error_msg = f"[WebReader] Trust gate DENIED for internal target {host} - {decision.message}"
                    self.memory.remember(error_msg, category="governance", priority=0.9)
                    
                    raise TrustDeniedError(
                        component=component_name,
                        action=NETWORK_ACCESS,
                        target=host,
                        reason=decision.reason_code,
                        context={**gate_context, "risk_score": decision.risk_score}
                    )
            else:
                # Normal external target or internal target without allow_internal (already blocked above)
                decision = self.trust_matrix.validate_trust_for_action(component_name, NETWORK_ACCESS, context=gate_context)
                
                if decision.decision == "deny":
                    # Trust gate denied - raise explicit exception
                    error_msg = f"[WebReader] Trust gate DENIED for {host} - {decision.message}"
                    self.memory.remember(error_msg, category="governance", priority=0.9)
                    
                    raise TrustDeniedError(
                        component=component_name,
                        action=NETWORK_ACCESS,
                        target=host,
                        reason=decision.reason_code,
                        context={**gate_context, "risk_score": decision.risk_score}
                    )
                elif decision.decision == "review":
                    # Borderline trust - enqueue review request
                    if self.review_queue:
                        review_request_id = self.review_queue.enqueue(
                            component=component_name,
                            action=NETWORK_ACCESS,
                            context=gate_context
                        )
                        
                        summary = f"Network access to {host} requires review (trust: {decision.risk_score:.2f})"
                        error_msg = f"[WebReader] Review request created: {review_request_id} - {summary}"
                        self.memory.remember(error_msg, category="governance", priority=0.8)
                        
                        raise TrustReviewRequiredError(
                            request_id=review_request_id,
                            component=component_name,
                            action=NETWORK_ACCESS,
                            target=host,
                            summary=summary,
                            context={**gate_context, "risk_score": decision.risk_score}
                        )
                    else:
                        # No review queue - treat as deny
                        raise TrustDeniedError(
                            component=component_name,
                            action=NETWORK_ACCESS,
                            target=host,
                            reason=decision.reason_code,
                            context={**gate_context, "risk_score": decision.risk_score}
                        )
        
        # Gate approved - proceed with network request
        try:
            response = self.session.get(url, timeout=10)
            
            if response.status_code != 200:
                self.memory.remember(
                    f"[WebReader] Failed to fetch: {url} (status {response.status_code})",
                    category="external",
                    priority=0.6
                )
                return None
                
            # Extract text content
            text = self._extract_text(response.text)
            
            if text:
                # Truncate if too long
                if len(text) > max_length:
                    text = text[:max_length] + "..."
                    
                self.memory.remember(
                    f"[Observation] {url} → {text[:100]}...",
                    category="external",
                    priority=0.7
                )
                return text
            else:
                self.memory.remember(
                    f"[WebReader] No content extracted from: {url}",
                    category="external",
                    priority=0.5
                )
                return None
                
        except Exception as e:
            error_msg = f"[WebReader Error] {url}: {str(e)}"
            self.memory.remember(error_msg, category="error", priority=0.7)
            return None
    
    def _redact_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """Redact sensitive header values before logging"""
        sensitive_keys = ["authorization", "token", "key", "secret", "api-key", "x-api-key", "cookie"]
        redacted = {}
        for k, v in headers.items():
            if any(sensitive in k.lower() for sensitive in sensitive_keys):
                redacted[k] = "[REDACTED]"
            else:
                redacted[k] = v
        return redacted
    
    def request_json(
        self,
        method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"],
        url: str,
        json_body: Optional[Dict[str, Any] | List[Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout_s: int = 30,
        caller_identity: Optional[str] = None,
        task_id: Optional[str] = None,
        request_id: Optional[str] = None,
        allow_internal: bool = False
    ) -> Dict[str, Any]:
        """
        Make an HTTP request with JSON support (POST/PUT/etc) through TrustMatrix gate.
        
        Args:
            method: HTTP method (GET, POST, PUT, PATCH, DELETE)
            url: URL to request
            json_body: Optional JSON body (dict or list)
            headers: Optional custom headers (will be redacted in logs)
            timeout_s: Request timeout in seconds
            caller_identity: Identity of the caller (for audit)
            task_id: Task ID if available (for audit)
            request_id: Optional request ID for replay approval
            allow_internal: If True, allow internal targets (requires TrustMatrix review/approval)
        
        Returns:
            Dict with keys: status_code, json (parsed JSON), text (raw text), headers (response headers)
        
        Raises:
            TrustDeniedError: If TrustMatrix denies the network request or target is blocked
            TrustReviewRequiredError: If TrustMatrix requires review
        """
        # SSRF SAFETY FLOOR: Validate scheme and target before TrustMatrix gating
        try:
            scheme, host, blocked_reason = self._validate_target(url, allow_internal=allow_internal)
        except TrustDeniedError:
            raise  # Re-raise validation errors
        
        # GOVERNANCE GATE: TrustMatrix must approve network request
        if self.trust_matrix is None:
            raise TrustDeniedError(
                component="WebReader",
                action=NETWORK_ACCESS,
                target=host or url,
                reason="TrustMatrix not available",
                context={"caller": caller_identity or "unknown", "task_id": task_id or "unknown", "method": method, "scheme": scheme, "allow_internal": allow_internal}
            )
        
        # Build context for trust gate
        gate_context = {
            "component": "WebReader",
            "action": NETWORK_ACCESS,
            "target": host,  # Use host, not full URL
            "scheme": scheme,
            "method": method,
            "has_body": json_body is not None,
            "content_type": "json" if json_body is not None else None,
            "allow_internal": allow_internal,
            "caller_identity": caller_identity or "unknown",
            "task_id": task_id or "unknown"
        }
        
        # Add blocked_reason if applicable
        if blocked_reason:
            gate_context["blocked_reason"] = blocked_reason
        
        # Check for replay: if request_id provided and approved, bypass review
        approved_replay = False
        if request_id and self.approval_store:
            if self.approval_store.is_approved(request_id, context=gate_context):
                # Approved request with matching context - proceed (skip gate check)
                self.memory.remember(
                    f"[WebReader] Using approved request {request_id} for {method} {host}",
                    category="governance",
                    priority=0.7
                )
                approved_replay = True
            else:
                # Request ID provided but not approved or context mismatch
                raise TrustDeniedError(
                    component="WebReader",
                    action=NETWORK_ACCESS,
                    target=host,
                    reason="APPROVAL_NOT_FOUND_OR_CONTEXT_MISMATCH",
                    context=gate_context
                )
        
        # Normal gate check (only if no approved request_id)
        if not approved_replay:
            component_name = "WebReader"
            
            # For internal targets with allow_internal=True, require review/approval
            # Even if TrustMatrix would auto-allow, internal targets need explicit review
            if blocked_reason and allow_internal:
                # Force review flow for internal targets
                decision = self.trust_matrix.validate_trust_for_action(component_name, NETWORK_ACCESS, context=gate_context)
                
                # Internal targets cannot be auto-allowed - require review or explicit approval
                if decision.decision == "allow":
                    # Even if TrustMatrix allows, log that this is an internal target override
                    self.memory.remember(
                        f"[WebReader] Internal target override approved: {method} {host} (trust: {decision.risk_score:.2f})",
                        category="governance",
                        priority=0.8
                    )
                    # Proceed with allow
                elif decision.decision == "review":
                    # Enqueue review request
                    if self.review_queue:
                        review_request_id = self.review_queue.enqueue(
                            component=component_name,
                            action=NETWORK_ACCESS,
                            context=gate_context
                        )
                        
                        summary = f"Internal target {method} {host} requires review (trust: {decision.risk_score:.2f})"
                        error_msg = f"[WebReader] Review request created: {review_request_id} - {summary}"
                        self.memory.remember(error_msg, category="governance", priority=0.8)
                        
                        raise TrustReviewRequiredError(
                            request_id=review_request_id,
                            component=component_name,
                            action=NETWORK_ACCESS,
                            target=host,
                            summary=summary,
                            context={**gate_context, "risk_score": decision.risk_score}
                        )
                    else:
                        # No review queue - treat as deny
                        raise TrustDeniedError(
                            component=component_name,
                            action=NETWORK_ACCESS,
                            target=host,
                            reason=decision.reason_code,
                            context={**gate_context, "risk_score": decision.risk_score}
                        )
                else:  # deny
                    # Trust gate denied - raise explicit exception
                    error_msg = f"[WebReader] Trust gate DENIED for internal target {method} {host} - {decision.message}"
                    self.memory.remember(error_msg, category="governance", priority=0.9)
                    
                    raise TrustDeniedError(
                        component=component_name,
                        action=NETWORK_ACCESS,
                        target=host,
                        reason=decision.reason_code,
                        context={**gate_context, "risk_score": decision.risk_score}
                    )
            else:
                # Normal external target or internal target without allow_internal (already blocked above)
                decision = self.trust_matrix.validate_trust_for_action(component_name, NETWORK_ACCESS, context=gate_context)
                
                if decision.decision == "deny":
                    # Trust gate denied - raise explicit exception
                    error_msg = f"[WebReader] Trust gate DENIED for {method} {host} - {decision.message}"
                    self.memory.remember(error_msg, category="governance", priority=0.9)
                    
                    raise TrustDeniedError(
                        component=component_name,
                        action=NETWORK_ACCESS,
                        target=host,
                        reason=decision.reason_code,
                        context={**gate_context, "risk_score": decision.risk_score}
                    )
                elif decision.decision == "review":
                    # Borderline trust - enqueue review request
                    if self.review_queue:
                        review_request_id = self.review_queue.enqueue(
                            component=component_name,
                            action=NETWORK_ACCESS,
                            context=gate_context
                        )
                        
                        summary = f"Network {method} request to {host} requires review (trust: {decision.risk_score:.2f})"
                        error_msg = f"[WebReader] Review request created: {review_request_id} - {summary}"
                        self.memory.remember(error_msg, category="governance", priority=0.8)
                        
                        raise TrustReviewRequiredError(
                            request_id=review_request_id,
                            component=component_name,
                            action=NETWORK_ACCESS,
                            target=host,
                            summary=summary,
                            context={**gate_context, "risk_score": decision.risk_score}
                        )
                    else:
                        # No review queue - treat as deny
                        raise TrustDeniedError(
                            component=component_name,
                            action=NETWORK_ACCESS,
                            target=host,
                            reason=decision.reason_code,
                            context={**gate_context, "risk_score": decision.risk_score}
                        )
        
        # Gate approved - proceed with network request
        try:
            # Prepare request
            req_headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                )
            }
            
            # Add custom headers (redact sensitive ones for logging)
            if headers:
                req_headers.update(headers)
            
            # Prepare body if JSON
            data = None
            if json_body is not None:
                data = json.dumps(json_body).encode('utf-8')
                req_headers["Content-Type"] = "application/json"
            
            # Create request
            req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
            
            # Log request (with redacted headers)
            redacted_headers = self._redact_headers(req_headers)
            self.memory.remember(
                f"[WebReader] {method} {host} (headers: {redacted_headers})",
                category="external",
                priority=0.6
            )
            
            # Execute request
            with urllib.request.urlopen(req, timeout=timeout_s) as response:
                status_code = response.getcode()
                response_headers = dict(response.headers)
                response_text = response.read().decode('utf-8', errors='replace')
                
                # Try to parse JSON
                response_json = None
                content_type = response_headers.get('Content-Type', '').lower()
                if 'json' in content_type or (response_text.strip().startswith('{') or response_text.strip().startswith('[')):
                    try:
                        response_json = json.loads(response_text)
                    except json.JSONDecodeError:
                        pass  # Not JSON, keep as text
                
                result = {
                    "status_code": status_code,
                    "json": response_json,
                    "text": response_text if response_json is None else None,
                    "headers": response_headers
                }
                
                self.memory.remember(
                    f"[WebReader] {method} {host} → {status_code}",
                    category="external",
                    priority=0.7
                )
                
                return result
                
        except urllib.error.HTTPError as e:
            # HTTP error (4xx, 5xx)
            status_code = e.code
            response_text = e.read().decode('utf-8', errors='replace') if hasattr(e, 'read') else str(e.reason)
            
            # Try to parse JSON error response
            response_json = None
            if response_text.strip().startswith('{') or response_text.strip().startswith('['):
                try:
                    response_json = json.loads(response_text)
                except json.JSONDecodeError:
                    pass
            
            result = {
                "status_code": status_code,
                "json": response_json,
                "text": response_text if response_json is None else None,
                "headers": dict(e.headers) if hasattr(e, 'headers') else {}
            }
            
            self.memory.remember(
                f"[WebReader] {method} {host} → {status_code} (error)",
                category="external",
                priority=0.6
            )
            
            return result
            
        except Exception as e:
            error_msg = f"[WebReader Error] {method} {url}: {str(e)}"
            self.memory.remember(error_msg, category="error", priority=0.7)
            raise
    
    def _extract_text(self, html_content: str) -> str:
        """
        Extract text content from HTML.
        
        Args:
            html_content: HTML content to parse
            
        Returns:
            Extracted text
        """
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, "html.parser")
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
                
            # Extract text from paragraphs and other text elements
            text_elements = soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "div"])
            text_parts = []
            
            for element in text_elements:
                text = element.get_text(strip=True)
                if text and len(text) > 10:  # Only meaningful text
                    text_parts.append(text)
                    
            return "\n".join(text_parts)
            
        except ImportError:
            # Fallback if BeautifulSoup is not available
            import re
            # Simple HTML tag removal
            text = re.sub(r'<[^>]+>', '', html_content)
            text = re.sub(r'\s+', ' ', text).strip()
            return text
    
    def get_web_stats(self) -> Dict[str, Any]:
        """
        Get web reader statistics.
        
        Returns:
            Web reader statistics
        """
        web_memories = self.memory.get_memories_by_category("external")
        
        return {
            "total_fetches": len(web_memories),
            "recent_fetches": [m["thought"] for m in web_memories[-5:]],
            "fetch_success_rate": len([m for m in web_memories if "Error" not in m["thought"]]) / max(1, len(web_memories))
        }

class VoiceThread:
    """
    Text-to-speech capabilities for Project Guardian.
    Provides voice interaction with personality modes.
    """
    
    def __init__(self, memory: MemoryCore, mode: str = "warm_guide", voice_index: int = 1):
        self.memory = memory
        self.mode = mode
        self.voice_index = voice_index
        self.lock = threading.Lock()
        self.speech_count = 0
        
        # Initialize text-to-speech engine
        try:
            self.engine = pyttsx3.init()
            voices = self.engine.getProperty('voices')
            if 0 <= voice_index < len(voices):
                self.engine.setProperty('voice', voices[voice_index].id)
        except Exception as e:
            self.memory.remember(
                f"[VoiceThread] Failed to initialize: {str(e)}",
                category="error",
                priority=0.6
            )
            self.engine = None
            
    def set_mode(self, mode: str) -> None:
        """
        Set voice personality mode.
        
        Args:
            mode: Voice mode (warm_guide, sharp_analyst, poetic_oracle)
        """
        self.mode = mode
        self.memory.remember(
            f"[VoiceThread] Mode changed to: {mode}",
            category="external",
            priority=0.5
        )
        
    def speak(self, text: str) -> None:
        """
        Speak text with current personality mode.
        
        Args:
            text: Text to speak
        """
        if not self.engine:
            print(f"[VoiceThread] Cannot speak: engine not available")
            return
            
        phrase = self._apply_voice_style(text)
        self.speech_count += 1
        
        # Speak in background thread
        threading.Thread(target=self._speak_safe, args=(phrase,), daemon=True).start()
        
        self.memory.remember(
            f"[VoiceThread] Spoke: {text[:50]}...",
            category="external",
            priority=0.6
        )
        
    def _speak_safe(self, phrase: str) -> None:
        """
        Safely speak text with error handling.
        
        Args:
            phrase: Text to speak
        """
        with self.lock:
            try:
                if self.engine:
                    self.engine.say(phrase)
                    self.engine.runAndWait()
            except Exception as e:
                error_msg = f"[VoiceThread] Speech error: {str(e)}"
                self.memory.remember(error_msg, category="error", priority=0.6)
                print(error_msg)
                
    def _apply_voice_style(self, text: str) -> str:
        """
        Apply personality style to text.
        
        Args:
            text: Original text
            
        Returns:
            Styled text
        """
        if self.mode == "warm_guide":
            return f"My dear friend, {text}"
        elif self.mode == "sharp_analyst":
            return f"Here's the concise truth: {text}"
        elif self.mode == "poetic_oracle":
            return f"As the stars turn, know this: {text}"
        elif self.mode == "guardian":
            return f"🛡️ Guardian speaks: {text}"
        else:
            return text
            
    def get_voice_stats(self) -> Dict[str, Any]:
        """
        Get voice thread statistics.
        
        Returns:
            Voice statistics dictionary
        """
        voice_memories = self.memory.get_memories_by_category("external")
        
        return {
            "speech_count": self.speech_count,
            "current_mode": self.mode,
            "voice_index": self.voice_index,
            "engine_available": self.engine is not None,
            "recent_speech": [m["thought"] for m in voice_memories[-3:] if "Spoke" in m["thought"]]
        }

class AIInteraction:
    """
    External AI interaction for Project Guardian.
    Provides ChatGPT integration and AI-powered assistance.
    """
    
    def __init__(self, memory: MemoryCore, api_key: Optional[str] = None):
        self.memory = memory
        self.api_key = api_key
        self.interaction_count = 0
        
        if self.api_key and openai:
            openai.api_key = self.api_key
            
    def ask_chatgpt(self, prompt: str, model: str = "gpt-3.5-turbo") -> str:
        """
        Ask ChatGPT a question.
        
        Args:
            prompt: Question or prompt
            model: Model to use
            
        Returns:
            AI response
        """
        if not self.api_key or not openai:
            return "Error: No OpenAI API key configured or openai module not available"
            
        try:
            self.memory.remember(
                f"[AI Interaction] Asking: {prompt[:50]}...",
                category="external",
                priority=0.7
            )
            
            response = openai.ChatCompletion.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )
            
            reply = response.choices[0].message["content"].strip()
            self.interaction_count += 1
            
            self.memory.remember(
                f"[AI Response] {reply[:100]}...",
                category="external",
                priority=0.7
            )
            
            return reply
            
        except Exception as e:
            error_msg = f"[AI Interaction Error] {str(e)}"
            self.memory.remember(error_msg, category="error", priority=0.8)
            return f"Error: {str(e)}"
            
    def get_ai_advice(self, context: str, question: str) -> str:
        """
        Get AI advice with context.
        
        Args:
            context: Context information
            question: Question to ask
            
        Returns:
            AI advice
        """
        prompt = f"""Context: {context}

Question: {question}

Please provide helpful advice based on the context."""
        
        return self.ask_chatgpt(prompt)
        
    def get_ai_stats(self) -> Dict[str, Any]:
        """
        Get AI interaction statistics.
        
        Returns:
            AI statistics dictionary
        """
        ai_memories = self.memory.get_memories_by_category("external")
        
        return {
            "interaction_count": self.interaction_count,
            "api_key_configured": bool(self.api_key),
            "recent_interactions": [m["thought"] for m in ai_memories[-5:] if "AI" in m["thought"]]
        } 