import zipfile
import re
import sys

docx_path = sys.argv[1]
with zipfile.ZipFile(docx_path, 'r') as z:
    with z.open('word/styles.xml') as f:
        content = f.read().decode('utf-8')

    # Find docDefaults
    doc_defaults = re.findall(r'<w:docDefaults>.*?</w:docDefaults>', content, re.DOTALL)
    print('=== DocDefaults ===')
    for d in doc_defaults:
        print(d[:2000])

    # Find style definitions with font info
    print('\n=== Style definitions with rFonts ===')
    styles = re.findall(r'<w:style[^>]*>.*?</w:style>', content, re.DOTALL)
    for s in styles:
        if 'rFonts' in s:
            style_id = re.findall(r'w:styleId="([^"]+)"', s)
            style_name = re.findall(r'<w:name w:val="([^"]+)"', s)
            fonts = re.findall(r'<w:rFonts[^/]*/?>', s)
            if style_id and fonts:
                print(f'  Style: {style_id[0]} ({style_name[0] if style_name else "?"}) -> {fonts[:3]}')