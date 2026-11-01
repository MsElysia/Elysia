"""Generate a source-derived inventory; does not claim browser verification."""
import ast
import csv
from pathlib import Path
import re
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = (ROOT / 'project_guardian/ui_control_panel.py').read_text(encoding='utf-8')
    module = ast.parse(source)
    template = next(ast.literal_eval(node.value) for node in module.body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'CONTROL_PANEL_TEMPLATE' for t in node.targets))
    routes = {}
    for node in ast.walk(module):
        if isinstance(node, ast.FunctionDef):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr == 'route' and decorator.args and isinstance(decorator.args[0], ast.Constant):
                    routes[decorator.args[0].value] = node.name
    soup = BeautifulSoup(template, 'html.parser')
    path = ROOT / 'docs/windows-ui-mission/controls.csv'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as output:
        writer = csv.writer(output)
        writer.writerow(['label', 'element_id', 'frontend_handler', 'api_paths_source_candidates', 'backend_route_functions', 'contained_availability', 'authorization', 'expected_visible_result', 'verification'])
        for control in soup.select('button, input, textarea, select'):
            label = control.get('aria-label') or control.get('title') or control.get_text(' ', strip=True) or control.get('placeholder') or control.get('id') or control.name
            handler = control.get('onclick') or control.get('onchange') or ''
            name = re.match(r'(\w+)\(', handler)
            body = ''
            if name:
                match = re.search(r'(?:window\.' + re.escape(name[1]) + r'\s*=\s*(?:async\s+)?function|function\s+' + re.escape(name[1]) + r')\([^)]*\)\s*\{(.*?)(?:\n        \};|\n        \})', template, re.S)
                body = match[1] if match else ''
            paths = sorted(set(re.findall(r"['\"](/api/[^'\"]+)['\"]", body)))
            availability = 'Requires runtime audit'
            if control.has_attr('disabled'):
                availability = 'Disabled or prerequisite-gated; inspect title'
            elif name and name[1] == 'showTab':
                availability = 'Navigation'
            elif control.find_parent(id='learning') or (name and name[1] in {'speakMessage', 'triggerDreamCycle', 'refreshIncomeStatus', 'runHarvestReport', 'runResearchProposal', 'runPromptEvolution'}):
                availability = 'Unavailable in this contained session'
            if any(p.startswith('/api/documents') for p in paths):
                auth = 'loopback + contained startup + dashboard operator token'
            elif any(p.startswith('/api/conversations') or p == '/api/chat' for p in paths):
                auth = 'loopback + contained startup; tools require request-scoped grants'
            else:
                auth = 'See backend gate; not inferred from UI availability'
            writer.writerow([label, control.get('id', ''), handler, ' | '.join(paths), ' | '.join(routes.get(p, 'dynamic route / nested handler') for p in paths), availability, auth, 'Visible result/status or explicitly unavailable; verify per control', 'SOURCE AUDIT ONLY'])
    print(f'Wrote {len(soup.select("button, input, textarea, select"))} controls to {path.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
