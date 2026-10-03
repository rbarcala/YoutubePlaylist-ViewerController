with open('patch_matrix_and_filter.py', 'r', encoding='utf-8') as f:
    code = f.read()

code = code.replace(
    'html = re.sub(pattern, sp_logic_code.strip(), html, count=1)',
    'html = re.sub(pattern, lambda m: sp_logic_code.strip(), html, count=1)'
)

with open('patch_matrix_and_filter.py', 'w', encoding='utf-8') as f:
    f.write(code)

print("fix_patch.py prepared.")
