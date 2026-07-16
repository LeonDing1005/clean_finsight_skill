import zipfile
import re

docx_path = r'C:\Users\dingly\.claude\skills\finsight-research\outputs\小商品城\小商品城（600415）：数字贸易生态闭环成型，估值逻辑迎来范式切换_20260713_163736.docx'

with zipfile.ZipFile(docx_path, 'r') as z:
    with z.open('word/document.xml') as f:
        doc = f.read().decode('utf-8')

    runs = re.findall(r'<w:r>(.*?)</w:r>', doc, re.DOTALL)

    # Separate runs by hint
    for hint_type, label in [
        ('eastAsia', 'East Asian hint'),
        ('', 'No hint'),
    ]:
        matching = []
        for r in runs:
            has_hint = ('w:hint="eastAsia"' in r) if hint_type == 'eastAsia' else ('w:hint=' not in r)
            if has_hint:
                font = re.findall(r'<w:rFonts([^>]*)/>', r)
                texts = re.findall(r'<w:t[^>]*>(.*?)</w:t>', r)
                txt = ''.join(texts)
                # Check if contains Latin chars or digits
                has_latin = bool(re.search(r'[a-zA-Z0-9]', txt))
                if has_latin:
                    matching.append((txt[:80], font))

        print(f'\n=== {label} runs with Latin/English/digits: {len(matching)} ===')
        for txt, font in matching[:10]:
            print(f'  font={font}, text="{txt}"')

    # Also check: are Latin chars in their own separate runs?
    print('\n=== All runs containing only Latin/digits/punctuation ===')
    latin_only = []
    for r in runs:
        texts = re.findall(r'<w:t[^>]*>(.*?)</w:t>', r)
        txt = ''.join(texts)
        if txt.strip() and re.match(r'^[\s\d\.,\%\$a-zA-Z\(\)\[\]\-\+\=]+$', txt.strip()):
            font = re.findall(r'<w:rFonts([^>]*)/>', r)
            has_hint = 'w:hint=' in r
            latin_only.append((txt.strip()[:60], font, 'hint' if has_hint else 'no-hint'))

    for txt, font, hint in latin_only[:15]:
        print(f'  [{hint}] font={font}, text="{txt}"')

    # Check how pandoc splits mixed Chinese+number in same paragraph
    print('\n=== Paragraphs with mixed content (sample) ===')
    paras = re.findall(r'<w:p[ >].*?</w:p>', doc, re.DOTALL)
    count = 0
    for p in paras:
        texts = re.findall(r'<w:t[^>]*>(.*?)</w:t>', p)
        full = ''.join(texts)
        has_cn = bool(re.search(r'[一-鿿]', full))
        has_latin = bool(re.search(r'[a-zA-Z0-9]', full))
        if has_cn and has_latin and count < 3:
            print(f'\n  --- Para {count} ---')
            # Show each run with its font hint
            para_runs = re.findall(r'<w:r>(.*?)</w:r>', p, re.DOTALL)
            for pr in para_runs:
                t = re.findall(r'<w:t[^>]*>(.*?)</w:t>', pr)
                txt = ''.join(t)
                hint_match = re.findall(r'w:hint="(\w+)"', pr)
                font_match = re.findall(r'<w:rFonts([^>]*)/>', pr)
                hint = hint_match[0] if hint_match else 'none'
                print(f'    hint={hint}, font={font_match}, text="{txt[:80]}"')
            count += 1