#!/usr/bin/env python3
"""
Proposal Management API
REST API endpoints for managing proposals via Architect-Core and WebScout.
"""

import logging
from typing import Dict, Any, Optional, List
from flask import Flask, request, jsonify
from flask_cors import CORS

logger = logging.getLogger(__name__)


class ProposalAPI:
    """REST API for proposal management"""
    
    def __init__(self, architect_core, host: str = "0.0.0.0", port: int = 5000):
        """
        Initialize the Proposal API.
        
        Args:
            architect_core: ArchitectCore instance
            host: Host to bind to
            port: Port to listen on
        """
        self.architect = architect_core
        self.app = Flask(__name__)
        CORS(self.app)  # Enable CORS for cross-origin requests
        
        # Register routes
        self._register_routes()
        
        self.host = host
        self.port = port
    
    def _register_routes(self):
        """Register API routes"""
        
        @self.app.route('/api/proposals', methods=['GET'])
        def list_proposals():
            """List all proposals, optionally filtered by status"""
            status_filter = request.args.get('status')
            proposals = self.architect.get_proposals(status_filter)
            return jsonify({
                "status": "success",
                "count": len(proposals),
                "proposals": proposals
            })
        
        @self.app.route('/api/proposals/<proposal_id>', methods=['GET'])
        def get_proposal(proposal_id: str):
            """Get a specific proposal"""
            proposal = self.architect.get_proposal(proposal_id)
            if proposal:
                return jsonify({
                    "status": "success",
                    "proposal": proposal
                })
            else:
                return jsonify({
                    "status": "error",
                    "message": f"Proposal {proposal_id} not found"
                }), 404
        
        @self.app.route('/api/proposals', methods=['POST'])
        def create_proposal():
            """Create a new research proposal"""
            data = request.get_json()
            
            if not data:
                return jsonify({
                    "status": "error",
                    "message": "No JSON data provided"
                }), 400
            
            task_description = data.get('task_description')
            topic = data.get('topic')
            
            if not task_description or not topic:
                return jsonify({
                    "status": "error",
                    "message": "Missing required fields: task_description, topic"
                }), 400
            
            result = self.architect.create_research_proposal(task_description, topic)
            return jsonify(result), 201 if result["status"] == "success" else 400
        
        @self.app.route('/api/proposals/<proposal_id>/research', methods=['POST'])
        def add_research(proposal_id: str):
            """Add research findings to a proposal"""
            data = request.get_json()
            
            if not data:
                return jsonify({
                    "status": "error",
                    "message": "No JSON data provided"
                }), 400
            
            sources = data.get('sources', [])
            summary = data.get('summary', '')
            
            if not sources:
                return jsonify({
                    "status": "error",
                    "message": "Missing required field: sources"
                }), 400
            
            result = self.architect.add_research_to_proposal(proposal_id, sources, summary)
            return jsonify(result), 200 if result["status"] == "success" else 400
        
        @self.app.route('/api/proposals/<proposal_id>/design', methods=['POST'])
        def add_design(proposal_id: str):
            """Add design documents to a proposal"""
            data = request.get_json()
            
            if not data:
                return jsonify({
                    "status": "error",
                    "message": "No JSON data provided"
                }), 400
            
            architecture = data.get('architecture', '')
            integration = data.get('integration', '')
            api_spec = data.get('api_spec')
            
            if not architecture or not integration:
                return jsonify({
                    "status": "error",
                    "message": "Missing required fields: architecture, integration"
                }), 400
            
            result = self.architect.add_design_to_proposal(
                proposal_id, architecture, integration, api_spec
            )
            return jsonify(result), 200 if result["status"] == "success" else 400
        
        @self.app.route('/api/proposals/<proposal_id>/implementation', methods=['POST'])
        def add_implementation(proposal_id: str):
            """Add implementation plan to a proposal"""
            data = request.get_json()
            
            if not data:
                return jsonify({
                    "status": "error",
                    "message": "No JSON data provided"
                }), 400
            
            todos = data.get('todos', [])
            patches = data.get('patches')
            tests = data.get('tests')
            
            if not todos:
                return jsonify({
                    "status": "error",
                    "message": "Missing required field: todos"
                }), 400
            
            result = self.architect.add_implementation_to_proposal(
                proposal_id, todos, patches, tests
            )
            return jsonify(result), 200 if result["status"] == "success" else 400
        
        @self.app.route('/api/proposals/<proposal_id>/approve', methods=['POST'])
        def approve_proposal(proposal_id: str):
            """Approve a proposal"""
            data = request.get_json() or {}
            approver = data.get('approver', 'system')
            
            result = self.architect.approve_proposal(proposal_id, approver)
            return jsonify(result), 200 if result["status"] == "success" else 400
        
        @self.app.route('/api/proposals/<proposal_id>/reject', methods=['POST'])
        def reject_proposal(proposal_id: str):
            """Reject a proposal"""
            data = request.get_json()
            
            if not data or 'reason' not in data:
                return jsonify({
                    "status": "error",
                    "message": "Missing required field: reason"
                }), 400
            
            reason = data.get('reason')
            result = self.architect.reject_proposal(proposal_id, reason)
            return jsonify(result), 200 if result["status"] == "success" else 400
        
        @self.app.route('/api/webscout/status', methods=['GET'])
        def get_webscout_status():
            """Get WebScout agent status"""
            status = self.architect.get_webscout_status()
            return jsonify(status)
        
        @self.app.route('/api/architect/status', methods=['GET'])
        def get_architect_status():
            """Get Architect-Core status report"""
            status = self.architect.get_status_report()
            return jsonify(status)
        
        @self.app.route('/health', methods=['GET'])
        def health_check():
            """Health check endpoint"""
            return jsonify({
                "status": "healthy",
                "service": "proposal-api"
            })
    
    def run(self, debug: bool = False):
        """Run the API server"""
        logger.info(f"Starting Proposal API on {self.host}:{self.port}")
        self.app.run(host=self.host, port=self.port, debug=debug)


# Example usage
if __name__ == "__main__":
    import sys
    from pathlib import Path
    
    # Add project root to path
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))
    
    from core_modules.elysia_core_comprehensive.architect_core import ArchitectCore
    
    # Initialize Architect-Core
    architect = ArchitectCore(enable_proposals=True, enable_webscout=True)
    
    # Create and run API
    api = ProposalAPI(architect, host="127.0.0.1", port=5000)
    api.run(debug=True)

