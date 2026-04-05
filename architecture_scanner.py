#!/usr/bin/env python3
"""
Architecture Scanner
====================
Comprehensive scan of all modules and their placement in the overall program architecture
"""

import os
import ast
import json
from pathlib import Path
from typing import Dict, List, Set, Tuple
from collections import defaultdict
import re


class ArchitectureScanner:
    def __init__(self, root_path: str):
        self.root_path = Path(root_path)
        self.modules: Dict[str, Dict] = {}
        self.imports: Dict[str, Set[str]] = {}
        self.dependencies: Dict[str, Set[str]] = defaultdict(set)
        self.architecture_layers: Dict[str, List[str]] = defaultdict(list)
        
    def scan_all_modules(self):
        """Scan all Python modules in the project"""
        print("🔍 Scanning project architecture...")
        print("=" * 70)
        
        # Key directories to scan
        directories = [
            "project_guardian",
            "core_modules",
            "extracted_modules",
            "elysia",
            "mesh",
        ]
        
        for directory in directories:
            dir_path = self.root_path / directory
            if dir_path.exists():
                print(f"\n📁 Scanning {directory}/...")
                self._scan_directory(dir_path, directory)
        
        # Also scan root level Python files
        print(f"\n📁 Scanning root level files...")
        for py_file in self.root_path.glob("*.py"):
            if py_file.name != "architecture_scanner.py":
                self._analyze_module(py_file, "root")
    
    def _scan_directory(self, directory: Path, category: str):
        """Scan a directory for Python modules"""
        for py_file in directory.rglob("*.py"):
            # Skip test files and backups
            if "test" in py_file.name.lower() or ".bak" in py_file.name:
                continue
            self._analyze_module(py_file, category)
    
    def _analyze_module(self, file_path: Path, category: str):
        """Analyze a single Python module"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Parse AST
            try:
                tree = ast.parse(content)
            except SyntaxError:
                return
            
            # Extract module information
            module_name = file_path.stem
            relative_path = str(file_path.relative_to(self.root_path))
            
            # Get imports
            imports = self._extract_imports(tree)
            
            # Get class and function definitions
            classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
            functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
            
            # Determine architecture layer
            layer = self._determine_layer(file_path, category, classes, functions)
            
            # Store module info
            self.modules[relative_path] = {
                "name": module_name,
                "path": relative_path,
                "category": category,
                "layer": layer,
                "classes": classes,
                "functions": functions,
                "imports": imports,
                "file_size": file_path.stat().st_size
            }
            
            # Build dependency graph
            for imp in imports:
                self.dependencies[relative_path].add(imp)
            
        except Exception as e:
            print(f"  ⚠️  Error analyzing {file_path}: {e}")
    
    def _extract_imports(self, tree: ast.AST) -> Set[str]:
        """Extract all imports from AST"""
        imports = set()
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split('.')[0])
        
        return imports
    
    def _determine_layer(self, file_path: Path, category: str, classes: List[str], functions: List[str]) -> str:
        """Determine which architecture layer this module belongs to"""
        path_str = str(file_path).lower()
        name_lower = file_path.stem.lower()
        
        # Core/Foundation Layer
        if any(x in name_lower for x in ['core', 'base', 'foundation', 'architect']):
            return "Core/Foundation"
        
        # Memory Layer
        if any(x in name_lower for x in ['memory', 'storage', 'vector', 'timeline']):
            return "Memory/Storage"
        
        # Trust/Safety Layer
        if any(x in name_lower for x in ['trust', 'safety', 'security', 'audit', 'policy']):
            return "Trust/Safety"
        
        # Decision Making Layer
        if any(x in name_lower for x in ['decision', 'reasoning', 'consultation', 'consensus']):
            return "Decision Making"
        
        # Task/Execution Layer
        if any(x in name_lower for x in ['task', 'executor', 'assignment', 'queue', 'mission']):
            return "Task/Execution"
        
        # Mutation/Evolution Layer
        if any(x in name_lower for x in ['mutation', 'evolution', 'mutation', 'self_evolver']):
            return "Mutation/Evolution"
        
        # Communication Layer
        if any(x in name_lower for x in ['voice', 'thread', 'api', 'server', 'communication']):
            return "Communication/API"
        
        # Learning/AI Layer
        if any(x in name_lower for x in ['learning', 'ai', 'neural', 'model', 'adversarial']):
            return "Learning/AI"
        
        # Integration Layer
        if any(x in name_lower for x in ['integration', 'adapter', 'bridge', 'connector']):
            return "Integration"
        
        # Monitoring/Health Layer
        if any(x in name_lower for x in ['monitor', 'health', 'heartbeat', 'runtime']):
            return "Monitoring/Health"
        
        # Financial Layer
        if any(x in name_lower for x in ['income', 'revenue', 'credit', 'budget', 'financial']):
            return "Financial"
        
        # UI/Interface Layer
        if any(x in name_lower for x in ['ui', 'interface', 'control', 'panel', 'web']):
            return "UI/Interface"
        
        # Default based on category
        category_map = {
            "project_guardian": "Core/Foundation",
            "core_modules": "Core/Foundation",
            "extracted_modules": "Decision Making",
            "elysia": "Core/Foundation",
            "mesh": "Integration"
        }
        
        return category_map.get(category, "Other")
    
    def analyze_architecture(self):
        """Analyze the overall architecture"""
        print("\n" + "=" * 70)
        print("📊 ARCHITECTURE ANALYSIS")
        print("=" * 70)
        
        # Group modules by layer
        for module_path, info in self.modules.items():
            self.architecture_layers[info['layer']].append(module_path)
        
        # Print layer breakdown
        print("\n🏗️  ARCHITECTURE LAYERS:")
        print("-" * 70)
        for layer, modules in sorted(self.architecture_layers.items()):
            print(f"\n{layer} ({len(modules)} modules):")
            for module in sorted(modules)[:10]:  # Show first 10
                mod_info = self.modules[module]
                print(f"  • {mod_info['name']} ({mod_info['category']})")
            if len(modules) > 10:
                print(f"  ... and {len(modules) - 10} more")
        
        # Analyze dependencies
        print("\n" + "=" * 70)
        print("🔗 DEPENDENCY ANALYSIS")
        print("=" * 70)
        
        # Find core dependencies
        core_modules = [m for m, info in self.modules.items() 
                       if info['layer'] == "Core/Foundation"]
        
        print(f"\n📦 Core modules: {len(core_modules)}")
        print("Most imported modules:")
        import_counts = defaultdict(int)
        for module_path, info in self.modules.items():
            for imp in info['imports']:
                import_counts[imp] += 1
        
        for module, count in sorted(import_counts.items(), key=lambda x: x[1], reverse=True)[:15]:
            print(f"  • {module}: {count} imports")
    
    def check_extracted_modules_integration(self):
        """Check if extracted modules are integrated"""
        print("\n" + "=" * 70)
        print("🔍 EXTRACTED MODULES INTEGRATION CHECK")
        print("=" * 70)
        
        extracted_modules = [
            "adversarial_ai_self_improvement",
            "trust_consultation_system",
            "decision_making_layer"
        ]
        
        for module_name in extracted_modules:
            print(f"\n📄 {module_name}:")
            
            # Check if imported anywhere
            found_imports = []
            for module_path, info in self.modules.items():
                if module_name in str(info['imports']).lower() or module_name in module_path.lower():
                    found_imports.append(module_path)
            
            if found_imports:
                print(f"  ✅ Found in: {len(found_imports)} locations")
                for loc in found_imports[:5]:
                    print(f"     • {loc}")
            else:
                print(f"  ⚠️  NOT INTEGRATED - No imports found")
                print(f"     Location: extracted_modules/{module_name}.py")
    
    def generate_architecture_map(self):
        """Generate a visual architecture map"""
        print("\n" + "=" * 70)
        print("🗺️  ARCHITECTURE MAP")
        print("=" * 70)
        
        map_data = {
            "layers": {},
            "modules_by_category": {},
            "extracted_modules_status": {},
            "integration_points": []
        }
        
        # Organize by layer
        for layer, modules in self.architecture_layers.items():
            map_data["layers"][layer] = {
                "count": len(modules),
                "modules": [self.modules[m]['name'] for m in modules[:20]]
            }
        
        # Organize by category
        categories = defaultdict(list)
        for module_path, info in self.modules.items():
            categories[info['category']].append(info['name'])
        
        for category, modules in categories.items():
            map_data["modules_by_category"][category] = {
                "count": len(modules),
                "modules": modules[:20]
            }
        
        # Check extracted modules
        extracted_path = self.root_path / "extracted_modules"
        if extracted_path.exists():
            for py_file in extracted_path.glob("*.py"):
                module_name = py_file.stem
                # Check if it's imported
                is_integrated = any(
                    module_name in str(info['imports']).lower() 
                    for info in self.modules.values()
                )
                map_data["extracted_modules_status"][module_name] = {
                    "exists": True,
                    "integrated": is_integrated,
                    "path": str(py_file.relative_to(self.root_path))
                }
        
        # Save map
        output_file = self.root_path / "architecture_map.json"
        with open(output_file, 'w') as f:
            json.dump(map_data, f, indent=2)
        
        print(f"\n✅ Architecture map saved to: {output_file}")
        
        return map_data
    
    def generate_report(self):
        """Generate comprehensive architecture report"""
        report = []
        report.append("=" * 70)
        report.append("ARCHITECTURE SCAN REPORT")
        report.append("=" * 70)
        report.append("")
        
        # Summary
        report.append(f"Total Modules Scanned: {len(self.modules)}")
        report.append(f"Architecture Layers: {len(self.architecture_layers)}")
        report.append("")
        
        # Layer breakdown
        report.append("LAYER BREAKDOWN:")
        report.append("-" * 70)
        for layer, modules in sorted(self.architecture_layers.items()):
            report.append(f"{layer}: {len(modules)} modules")
        report.append("")
        
        # Extracted modules status
        report.append("EXTRACTED MODULES STATUS:")
        report.append("-" * 70)
        extracted_path = self.root_path / "extracted_modules"
        if extracted_path.exists():
            for py_file in extracted_path.glob("*.py"):
                module_name = py_file.stem
                is_integrated = any(
                    module_name in str(info['imports']).lower() 
                    for info in self.modules.values()
                )
                status = "✅ INTEGRATED" if is_integrated else "⚠️  NOT INTEGRATED"
                report.append(f"{module_name}: {status}")
        report.append("")
        
        # Integration recommendations
        report.append("INTEGRATION RECOMMENDATIONS:")
        report.append("-" * 70)
        
        # Check where extracted modules should be integrated
        extracted_modules = {
            "adversarial_ai_self_improvement": ["Trust/Safety", "Learning/AI"],
            "trust_consultation_system": ["Trust/Safety", "Decision Making"],
            "decision_making_layer": ["Decision Making"]
        }
        
        for module_name, target_layers in extracted_modules.items():
            report.append(f"\n{module_name}:")
            report.append(f"  Should integrate into: {', '.join(target_layers)}")
            
            # Find potential integration points
            integration_points = []
            for layer in target_layers:
                if layer in self.architecture_layers:
                    integration_points.extend(self.architecture_layers[layer][:3])
            
            if integration_points:
                report.append(f"  Potential integration points:")
                for point in integration_points[:3]:
                    report.append(f"    • {point}")
        
        report.append("")
        report.append("=" * 70)
        
        # Save report
        report_file = self.root_path / "architecture_scan_report.txt"
        with open(report_file, 'w') as f:
            f.write('\n'.join(report))
        
        print('\n'.join(report))
        print(f"\n✅ Full report saved to: {report_file}")


def main():
    root_path = Path(__file__).parent
    scanner = ArchitectureScanner(root_path)
    
    # Run scan
    scanner.scan_all_modules()
    
    # Analyze
    scanner.analyze_architecture()
    
    # Check extracted modules
    scanner.check_extracted_modules_integration()
    
    # Generate map and report
    scanner.generate_architecture_map()
    scanner.generate_report()
    
    print("\n" + "=" * 70)
    print("✅ Architecture scan complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
