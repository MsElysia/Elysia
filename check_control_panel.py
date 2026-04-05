"""Quick check of control panel template and script."""
import sys
sys.path.insert(0, '.')

try:
    from flask import Flask, render_template_string
    from project_guardian.ui_control_panel import CONTROL_PANEL_TEMPLATE

    app = Flask(__name__)
    with app.app_context():
        html = render_template_string(CONTROL_PANEL_TEMPLATE)
    # Find inline script block (has our code, not external src=)
    marker = '// Define addLog function FIRST'
    idx = html.find(marker)
    if idx >= 0:
        start = html.rfind('<script>', 0, idx)
        end = html.find('</script>', idx)
        script = html[start:end] if start >= 0 and end > start else html[idx:idx+5000]
    else:
        script = ''

    issues = []
    if '=>' in script:
        issues.append('Arrow functions (=>)')
    if '?.' in script:
        issues.append('Optional chaining (?.)')
    if "split('\\n')" in script or 'split("\\n")' in script:
        issues.append('Unescaped split/join with \\n')

    print('=== Control Panel Check ===')
    print('HTML length:', len(html))
    print('Script length:', len(script))
    print('showTab defined:', 'window.showTab' in script)
    print('toggleTheme defined:', 'window.toggleTheme' in script)
    print('Issues:', issues if issues else 'None')
    
    # Fetch via HTTP if server is already running
    try:
        import urllib.request
        req = urllib.request.Request('http://127.0.0.1:5000/', headers={'User-Agent': 'Check/1.0'})
        with urllib.request.urlopen(req, timeout=5) as f:
            body = f.read().decode()
        has_script = 'window.showTab' in body and 'window.toggleTheme' in body
        print('Live server (5000): OK | showTab+toggleTheme:', has_script)
    except Exception as e:
        print('Live server: not running or different port (run Project Guardian to test in browser)')
    
    print('PASS - Template valid' if not issues else 'Review issues above')
except Exception as e:
    print('Error:', e)
    import traceback
    traceback.print_exc()
