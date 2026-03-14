"""
Perception Module - Phase 2.1

Implements GUI-Actor coordinate-free grounding methodology.
Combines AT-SPI2, Tesseract OCR, and GUI-Actor attention mechanisms.
"""

import logging
import os
import time
from typing import Dict, List, Optional, Tuple, Any
import numpy as np

logger = logging.getLogger("cecil.perception")


class GUIActorGrounding:
    """
    GUI-Actor coordinate-free visual grounding implementation.
    Uses attention mechanisms instead of raw coordinates.
    """
    
    def __init__(self):
        self.actor_token = "<ACTOR>"
        self.attention_weights = {}
        self.regions_cache = {}
        self.last_screenshot = None
        
    def generate_attention_map(self, elements: List[Dict], screenshot_path: str) -> Dict:
        """
        Generate attention map for GUI elements using GUI-Actor methodology.
        Returns semantic regions with attention weights.
        """
        try:
            attention_map = {}
            
            for i, element in enumerate(elements):
                # Generate semantic region ID
                region_id = self._generate_semantic_region_id(element, i)
                
                # Calculate attention weight based on element properties
                attention_weight = self._calculate_attention_weight(element)
                
                # Store semantic region
                attention_map[region_id] = {
                    "element": element,
                    "attention_weight": attention_weight,
                    "semantic_type": element.get("role", "unknown"),
                    "label": element.get("name", ""),
                    "bounds": element.get("bounds", {}),
                    "interactable": self._is_interactable(element)
                }
            
            # Store cache
            self.attention_weights[screenshot_path] = attention_map
            self.last_screenshot = screenshot_path
            
            return attention_map
            
        except Exception as e:
            logger.error(f"GUI-Actor attention map generation failed: {e}")
            return {}
    
    def _generate_semantic_region_id(self, element: Dict, index: int) -> str:
        """Generate semantic region identifier (coordinate-free)."""
        elem_type = element.get("role", "unknown").lower()
        elem_name = element.get("name", "").lower().replace(" ", "_")
        
        # Create semantic identifier
        if elem_name:
            return f"{elem_type}_{elem_name}_{index}"
        else:
            return f"{elem_type}_{index}"
    
    def _calculate_attention_weight(self, element: Dict) -> float:
        """Calculate attention weight for element based on various factors."""
        weight = 0.5  # Base weight
        
        # Boost for interactable elements
        if self._is_interactable(element):
            weight += 0.3
        
        # Boost for elements with descriptive names
        name = element.get("name", "")
        if name and len(name) > 3:
            weight += 0.1
        
        # Boost for common UI elements
        role = element.get("role", "").lower()
        if role in ["button", "text", "menu", "link"]:
            weight += 0.1
        
        # Normalize to [0, 1]
        return min(max(weight, 0.0), 1.0)
    
    def _is_interactable(self, element: Dict) -> bool:
        """Determine if element is interactable."""
        interactable_roles = {"button", "text", "menu", "link", "checkbox", "radio", "slider"}
        return element.get("role", "").lower() in interactable_roles
    
    def get_top_regions(self, attention_map: Dict, limit: int = 10) -> List[Dict]:
        """Get top regions by attention weight."""
        regions = list(attention_map.values())
        regions.sort(key=lambda x: x["attention_weight"], reverse=True)
        return regions[:limit]
    
    def find_region_by_label(self, attention_map: Dict, label: str) -> Optional[Dict]:
        """Find region by label (case-insensitive partial match)."""
        label_lower = label.lower()
        
        for region in attention_map.values():
            region_label = region["label"].lower()
            if label_lower in region_label or region_label in label_lower:
                return region
        
        return None
    
    def find_regions_by_type(self, attention_map: Dict, elem_type: str) -> List[Dict]:
        """Find all regions of a specific type."""
        elem_type_lower = elem_type.lower()
        return [region for region in attention_map.values() 
                if region["semantic_type"].lower() == elem_type_lower]


class CoordinateFreeParser:
    """
    Enhanced screen parser with coordinate-free grounding.
    Combines traditional parsing with GUI-Actor methodology.
    """
    
    def __init__(self, traditional_parser, screen_capture):
        self.traditional_parser = traditional_parser
        self.screen_capture = screen_capture
        self.gui_actor = GUIActorGrounding()
        self.last_parse_time = 0
        self.parse_cache = {}
        
    def parse_screen_coordinate_free(self, screenshot_path: str = None) -> Dict:
        """
        Parse screen with coordinate-free grounding.
        Returns both traditional elements and semantic regions.
        """
        try:
            current_time = time.time()
            
            # Check cache
            if screenshot_path and screenshot_path in self.parse_cache:
                if current_time - self.parse_cache[screenshot_path]["timestamp"] < 5.0:
                    return self.parse_cache[screenshot_path]["data"]
            
            # Capture screenshot if not provided
            if not screenshot_path:
                screenshot_path = self.screen_capture.capture()
            
            # Traditional parsing
            traditional_elements = self.traditional_parser.parse(screenshot_path)
            
            # GUI-Actor coordinate-free grounding
            attention_map = self.gui_actor.generate_attention_map(traditional_elements, screenshot_path)
            
            # Combine results
            coordinate_free_data = {
                "screenshot_path": screenshot_path,
                "timestamp": current_time,
                "traditional_elements": traditional_elements,
                "semantic_regions": attention_map,
                "top_regions": self.gui_actor.get_top_regions(attention_map),
                "interactable_regions": [r for r in attention_map.values() if r["interactable"]],
                "parse_stats": {
                    "total_elements": len(traditional_elements),
                    "semantic_regions": len(attention_map),
                    "interactable_regions": len([r for r in attention_map.values() if r["interactable"]]),
                    "parse_time": current_time
                }
            }
            
            # Cache results
            self.parse_cache[screenshot_path] = {
                "timestamp": current_time,
                "data": coordinate_free_data
            }
            
            self.last_parse_time = current_time
            
            return coordinate_free_data
            
        except Exception as e:
            logger.error(f"Coordinate-free parsing failed: {e}")
            return {"error": str(e)}
    
    def find_element_coordinate_free(self, query: str, screenshot_path: str = None) -> Optional[Dict]:
        """
        Find element using coordinate-free semantic search.
        Returns semantic region instead of raw coordinates.
        """
        try:
            parse_data = self.parse_screen_coordinate_free(screenshot_path)
            
            if "error" in parse_data:
                return None
            
            semantic_regions = parse_data["semantic_regions"]
            
            # Try exact label match first
            region = self.gui_actor.find_region_by_label(semantic_regions, query)
            if region:
                return region
            
            # Try type-based search
            if any(keyword in query.lower() for keyword in ["button", "botón"]):
                button_regions = self.gui_actor.find_regions_by_type(semantic_regions, "button")
                if button_regions:
                    return button_regions[0]
            
            if any(keyword in query.lower() for keyword in ["text", "campo", "input"]):
                text_regions = self.gui_actor.find_regions_by_type(semantic_regions, "text")
                if text_regions:
                    return text_regions[0]
            
            # Fallback to top regions
            top_regions = parse_data["top_regions"]
            if top_regions:
                return top_regions[0]
            
            return None
            
        except Exception as e:
            logger.error(f"Coordinate-free element search failed: {e}")
            return None
    
    def generate_context_for_planning(self, screenshot_path: str = None) -> str:
        """
        Generate coordinate-free context for planning systems.
        Focuses on semantic regions rather than coordinates.
        """
        try:
            parse_data = self.parse_screen_coordinate_free(screenshot_path)
            
            if "error" in parse_data:
                return "Screen parsing unavailable"
            
            context_lines = [
                "Coordinate-Free Screen Analysis:",
                "",
                f"Total Elements: {parse_data['parse_stats']['total_elements']}",
                f"Semantic Regions: {parse_data['parse_stats']['semantic_regions']}",
                f"Interactable Regions: {parse_data['parse_stats']['interactable_regions']}",
                "",
                "Top Semantic Regions:"
            ]
            
            for i, region in enumerate(parse_data["top_regions"][:10]):
                context_lines.append(
                    f"{i+1}. {region['semantic_type']}: '{region['label']}' "
                    f"(attention: {region['attention_weight']:.2f})"
                )
            
            return "\n".join(context_lines)
            
        except Exception as e:
            logger.error(f"Context generation failed: {e}")
            return "Context generation failed"


class PerceptionModule:
    """
    Main perception module orchestrating all vision and parsing capabilities.
    Integrates traditional vision with GUI-Actor coordinate-free grounding.
    """
    
    def __init__(self, vision_parser, screen_capture):
        self.vision_parser = vision_parser
        self.screen_capture = screen_capture
        self.coordinate_free_parser = CoordinateFreeParser(vision_parser, screen_capture)
        self.stats = {
            "total_parses": 0,
            "coordinate_free_parses": 0,
            "cache_hits": 0,
            "avg_parse_time": 0.0
        }
        
    def parse_screen(self, use_coordinate_free: bool = True, screenshot_path: str = None) -> Dict:
        """
        Parse screen using appropriate methodology.
        """
        self.stats["total_parses"] += 1
        
        if use_coordinate_free:
            self.stats["coordinate_free_parses"] += 1
            return self.coordinate_free_parser.parse_screen_coordinate_free(screenshot_path)
        else:
            # Traditional parsing
            elements = self.vision_parser.parse(screenshot_path)
            return {
                "traditional_elements": elements,
                "element_count": len(elements),
                "coordinate_free": False
            }
    
    def find_element(self, query: str, use_coordinate_free: bool = True, screenshot_path: str = None) -> Optional[Dict]:
        """
        Find element using appropriate search methodology.
        """
        if use_coordinate_free:
            return self.coordinate_free_parser.find_element_coordinate_free(query, screenshot_path)
        else:
            # Traditional element search
            elements = self.vision_parser.parse(screenshot_path)
            for element in elements:
                if query.lower() in element.get("name", "").lower():
                    return element
            return None
    
    def generate_planning_context(self, use_coordinate_free: bool = True, screenshot_path: str = None) -> str:
        """
        Generate context for planning systems.
        """
        if use_coordinate_free:
            return self.coordinate_free_parser.generate_context_for_planning(screenshot_path)
        else:
            # Traditional context
            elements = self.vision_parser.parse(screenshot_path)
            context_lines = [
                "Traditional Screen Analysis:",
                f"Total Elements: {len(elements)}",
                ""
            ]
            
            for i, element in enumerate(elements[:10]):
                context_lines.append(f"{i+1}. {element.get('role', 'unknown')}: '{element.get('name', '')}'")
            
            return "\n".join(context_lines)
    
    def get_stats(self) -> Dict:
        """Get perception module statistics."""
        return self.stats.copy()
    
    def clear_cache(self):
        """Clear parsing cache."""
        self.coordinate_free_parser.parse_cache.clear()
        self.coordinate_free_parser.gui_actor.regions_cache.clear()
