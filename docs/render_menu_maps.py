"""Optional PNG export: requires Playwright and an installed Chromium browser.

Example: python docs/render_menu_maps.py --browser /path/to/chromium
Without --browser, Playwright uses its configured bundled browser. No downloads.
"""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser', help='Absolute path to an installed Chromium executable')
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright
    here = Path(__file__).resolve().parent / 'menu-maps'
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    records = {}
    with sync_playwright() as p:
        options = {'headless': True}
        if args.browser:
            options['executable_path'] = args.browser
        browser = p.chromium.launch(**options)
        page = browser.new_page(viewport={'width': 1800, 'height': 1100}, device_scale_factor=1)
        for svg in sorted(here.glob('*.svg')):
            page.goto(svg.as_uri())
            page.wait_for_function('document.fonts.status === "loaded"')
            issues = page.evaluate('''() => {
                const s=document.querySelector('svg'), b=s.getBoundingClientRect();
                return [...s.querySelectorAll('text')].filter(t=>{
                    const r=t.getBoundingClientRect();
                    return r.right>b.right-18 || r.left<0 || r.bottom>b.bottom;
                }).map(t=>t.textContent);
            }''')
            if issues:
                raise RuntimeError(str(svg) + ': clipped text ' + repr(issues))
            png = svg.with_suffix('.png')
            page.locator('svg').screenshot(path=str(png))
            records[svg.stem] = {'svg_sha256': sha(svg), 'png_sha256': sha(png), 'clipped_text': issues}
        browser.close()
    (here / 'png-manifest.json').write_text(json.dumps(records, indent=2) + '\n', encoding='utf8')
    print(str(len(records)) + ' PNGs exported; SVG/PNG pairs hashed and text bounds checked.')


if __name__ == '__main__':
    main()
