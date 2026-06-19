html = '/home/ubuntu/wbtrade/static/index.html'
with open(html) as f:
    src = f.read()

if 'importBybitCSV' not in src:
    old_btn = '<button class="btn btn-primary btn-sm" onclick="openTradeModal()"><i class="ti ti-plus"></i> Log trade</button>'
    new_btns = (
        old_btn
        + '\n        <button class="btn btn-sm" style="margin-left:8px"'
        + ' onclick="document.getElementById(\'bybit-csv-input\').click()">'
        + '<i class="ti ti-upload"></i> Import CSV</button>'
        + '\n        <input type="file" id="bybit-csv-input" accept=".csv"'
        + ' style="display:none" onchange="importBybitCSV(this)">'
    )
    src = src.replace(old_btn, new_btns)
    js = (
        '<script>\nasync function importBybitCSV(inp){\n'
        '  const file=inp.files[0];if(!file)return;\n'
        '  const fd=new FormData();fd.append("file",file);inp.value="";\n'
        '  try{\n'
        '    const r=await fetch("/trade/api/trades/import",{method:"POST",body:fd});\n'
        '    const d=await r.json();\n'
        '    alert("Imported: "+d.inserted+" trades | Skipped: "+d.skipped+" duplicates"'
        '+(d.errors&&d.errors.length?"\\nErrors: "+d.errors.join(", "):""));\n'
        '    if(d.inserted>0)location.reload();\n'
        '  }catch(e){alert("Import failed: "+e.message);}\n'
        '}\n</script>\n</body>'
    )
    src = src.replace('</body>', js)
    with open(html, 'w') as f:
        f.write(src)
    print('index.html patched OK')
else:
    print('Already patched')
