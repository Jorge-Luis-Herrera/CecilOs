"""
MCP (Model Context Protocol) Bridge for OpenClaw Integration

Provides standardized tool discovery and integration with OpenClaw ecosystem.
Enables dynamic loading of 600+ tools from OpenClaw marketplace.
"""

import json
import logging
import os
import subprocess
import time
from typing import Dict, List, Optional, Any

logger = logging.getLogger("cecil.mcp_bridge")


class MCPTool:
    """Represents a single MCP tool with metadata and capabilities."""
    
    def __init__(self, tool_data: Dict):
        self.id = tool_data.get("id", "")
        self.name = tool_data.get("name", "")
        self.description = tool_data.get("description", "")
        self.category = tool_data.get("category", "")
        self.input_schema = tool_data.get("inputSchema", {})
        self.output_schema = tool_data.get("outputSchema", {})
        self.is_available = tool_data.get("available", True)
        self.version = tool_data.get("version", "1.0.0")
        self.author = tool_data.get("author", "")
        self.tags = tool_data.get("tags", [])
        
    def to_openclaw_format(self) -> Dict:
        """Convert MCP tool to OpenClaw-compatible format."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "input_schema": self.input_schema,
            "parameters": self._extract_parameters(),
            "available": self.is_available
        }
    
    def _extract_parameters(self) -> List[Dict]:
        """Extract parameters from input schema."""
        params = []
        properties = self.input_schema.get("properties", {})
        required = self.input_schema.get("required", [])
        
        for param_name, param_schema in properties.items():
            param = {
                "name": param_name,
                "type": param_schema.get("type", "string"),
                "description": param_schema.get("description", ""),
                "required": param_name in required,
                "default": param_schema.get("default")
            }
            params.append(param)
        
        return params


class MCPBridge:
    """
    Bridge between CecilOs and MCP (Model Context Protocol) ecosystem.
    Enables discovery and usage of OpenClaw marketplace tools.
    """
    
    def __init__(self, openclaw_path: str = None):
        self.openclaw_path = openclaw_path or self._find_openclaw()
        self.tools_cache = {}
        self.last_discovery = 0
        self.discovery_interval = 3600  # 1 hour
        self.stats = {
            "tools_discovered": 0,
            "tools_used": 0,
            "mcp_calls": 0,
            "errors": 0
        }
        
    def _find_openclaw(self) -> str:
        """Find OpenClaw CLI path."""
        import shutil
        candidates = [
            "openclaw",
            os.path.expanduser("~/.npm-global/bin/openclaw"),
            "/usr/local/bin/openclaw"
        ]
        for c in candidates:
            if shutil.which(c) or os.path.isfile(c):
                return c
        return ""
    
    def discover_tools(self, force_refresh: bool = False) -> List[MCPTool]:
        """
        Discover available MCP tools from OpenClaw ecosystem.
        Caches results for performance.
        """
        current_time = time.time()
        
        # Return cached results if still valid
        if not force_refresh and (current_time - self.last_discovery) < self.discovery_interval:
            return list(self.tools_cache.values())
        
        try:
            self.stats["mcp_calls"] += 1
            
            # Call OpenClaw MCP discovery
            result = subprocess.run(
                [self.openclaw_path, "mcp", "discover"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                logger.error(f"MCP discovery failed: {result.stderr}")
                self.stats["errors"] += 1
                return []
            
            # Parse tool data
            tool_data = json.loads(result.stdout)
            tools = []
            
            for tool_info in tool_data.get("tools", []):
                tool = MCPTool(tool_info)
                self.tools_cache[tool.id] = tool
                tools.append(tool)
            
            self.last_discovery = current_time
            self.stats["tools_discovered"] = len(tools)
            
            logger.info(f"Discovered {len(tools)} MCP tools")
            return tools
            
        except Exception as e:
            logger.error(f"MCP discovery error: {e}")
            self.stats["errors"] += 1
            return []
    
    def get_tool_by_id(self, tool_id: str) -> Optional[MCPTool]:
        """Get specific tool by ID."""
        tools = self.discover_tools()
        return tools.get(tool_id)
    
    def search_tools(self, query: str, category: str = None, 
                    tags: List[str] = None) -> List[MCPTool]:
        """Search tools by query, category, or tags."""
        tools_dict = self.discover_tools()
        results = []
        
        query_lower = query.lower()
        
        for tool in tools_dict:
            # Skip unavailable tools
            if not tool.is_available:
                continue
            
            # Category filter
            if category and tool.category.lower() != category.lower():
                continue
            
            # Tags filter
            if tags and not any(tag.lower() in [t.lower() for t in tool.tags] for tag in tags):
                continue
            
            # Text search
            searchable_text = f"{tool.name} {tool.description}".lower()
            if query_lower in searchable_text:
                results.append(tool)
        
        return results
    
    def execute_tool(self, tool_id: str, parameters: Dict) -> Dict:
        """
        Execute MCP tool with given parameters.
        Returns execution result.
        """
        try:
            self.stats["tools_used"] += 1
            self.stats["mcp_calls"] += 1
            
            # Prepare execution request
            execution_data = {
                "toolId": tool_id,
                "parameters": parameters,
                "context": "cecilos_integration"
            }
            
            # Call OpenClaw MCP execution
            result = subprocess.run(
                [self.openclaw_path, "mcp", "execute"],
                input=json.dumps(execution_data),
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                logger.error(f"MCP execution failed: {result.stderr}")
                self.stats["errors"] += 1
                return {
                    "success": False,
                    "error": result.stderr,
                    "tool_id": tool_id
                }
            
            # Parse execution result
            execution_result = json.loads(result.stdout)
            
            return {
                "success": True,
                "result": execution_result,
                "tool_id": tool_id,
                "execution_time": time.time()
            }
            
        except Exception as e:
            logger.error(f"MCP execution error: {e}")
            self.stats["errors"] += 1
            return {
                "success": False,
                "error": str(e),
                "tool_id": tool_id
            }
    
    def get_tool_categories(self) -> List[str]:
        """Get list of available tool categories."""
        tools_dict = self.discover_tools()
        categories = set()
        
        for tool in tools_dict:
            if tool.category:
                categories.add(tool.category)
        
        return sorted(list(categories))
    
    def get_popular_tools(self, limit: int = 10) -> List[MCPTool]:
        """Get popular tools based on usage statistics."""
        tools_dict = self.discover_tools()
        
        # Sort by a combination of factors (name recognition, tags, etc.)
        # For now, return tools with common tags
        popular_tags = ["browser", "file", "system", "automation", "productivity"]
        popular_tools = []
        
        for tool in tools_dict:
            if any(tag in tool.tags for tag in popular_tags):
                popular_tools.append(tool)
        
        return popular_tools[:limit]
    
    def generate_tool_context_for_openclaw(self, relevant_tools: List[MCPTool] = None) -> str:
        """
        Generate tool context string for OpenClaw planning.
        Includes relevant tools and their capabilities.
        """
        if relevant_tools is None:
            # Get popular tools as default
            relevant_tools = self.get_popular_tools(20)
        
        context_lines = [
            "Available MCP Tools (Model Context Protocol):",
            ""
        ]
        
        for tool in relevant_tools:
            context_lines.append(f"- {tool.name} ({tool.id}): {tool.description}")
            
            if tool.tags:
                context_lines.append(f"  Tags: {', '.join(tool.tags)}")
            
            # Add key parameters
            key_params = [p["name"] for p in tool.to_openclaw_format()["parameters"][:3]]
            if key_params:
                context_lines.append(f"  Key parameters: {', '.join(key_params)}")
            
            context_lines.append("")
        
        return "\n".join(context_lines)
    
    def get_stats(self) -> Dict:
        """Get MCP bridge statistics."""
        return {
            **self.stats,
            "cached_tools": len(self.tools_cache),
            "last_discovery": self.last_discovery,
            "discovery_interval": self.discovery_interval
        }
    
    def is_available(self) -> bool:
        """Check if MCP bridge is available."""
        return bool(self.openclaw_path)
    
    def refresh_cache(self):
        """Force refresh of tools cache."""
        self.discover_tools(force_refresh=True)


class MCPToolRegistry:
    """
    Registry for managing MCP tools and their integration with CecilOs.
    Provides tool lifecycle management and usage tracking.
    """
    
    def __init__(self, mcp_bridge: MCPBridge):
        self.mcp_bridge = mcp_bridge
        self.usage_history = []
        self.favorite_tools = set()
        self.tool_performance = {}
        
    def register_tool_usage(self, tool_id: str, success: bool, execution_time: float):
        """Register tool usage for performance tracking."""
        usage_record = {
            "tool_id": tool_id,
            "timestamp": time.time(),
            "success": success,
            "execution_time": execution_time
        }
        self.usage_history.append(usage_record)
        
        # Update performance metrics
        if tool_id not in self.tool_performance:
            self.tool_performance[tool_id] = {
                "total_uses": 0,
                "successful_uses": 0,
                "total_time": 0.0,
                "avg_time": 0.0,
                "success_rate": 0.0
            }
        
        perf = self.tool_performance[tool_id]
        perf["total_uses"] += 1
        perf["total_time"] += execution_time
        
        if success:
            perf["successful_uses"] += 1
        
        perf["avg_time"] = perf["total_time"] / perf["total_uses"]
        perf["success_rate"] = perf["successful_uses"] / perf["total_uses"]
    
    def get_recommended_tools(self, task_type: str, limit: int = 5) -> List[MCPTool]:
        """Get recommended tools based on task type and performance."""
        all_tools = self.mcp_bridge.discover_tools()
        
        # Filter by task relevance (tags, category, description)
        relevant_tools = []
        task_keywords = task_type.lower().split()
        
        for tool in all_tools.values():
            if not tool.is_available:
                continue
            
            # Check relevance
            tool_text = f"{tool.name} {tool.description} {' '.join(tool.tags)}".lower()
            if any(keyword in tool_text for keyword in task_keywords):
                relevant_tools.append(tool)
        
        # Sort by performance metrics
        def sort_key(tool):
            perf = self.tool_performance.get(tool.id, {})
            return (
                perf.get("success_rate", 0.5),
                -perf.get("avg_time", 100),  # Negative for ascending sort
                tool.name  # Tie-breaker
            )
        
        relevant_tools.sort(key=sort_key, reverse=True)
        
        return relevant_tools[:limit]
    
    def add_favorite(self, tool_id: str):
        """Add tool to favorites."""
        self.favorite_tools.add(tool_id)
    
    def remove_favorite(self, tool_id: str):
        """Remove tool from favorites."""
        self.favorite_tools.discard(tool_id)
    
    def get_favorites(self) -> List[MCPTool]:
        """Get favorite tools."""
        tools = self.mcp_bridge.discover_tools()
        return [tools[tool_id] for tool_id in self.favorite_tools if tool_id in tools]
