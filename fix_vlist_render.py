import re

with open('web_app/templates/index.html', 'r') as f:
    content = f.read()

# Replace the renderItem function to use the original CSS classes
old_render = '''                    renderItem: (item) => {
                        if (item.type === 'category') {
                            return `<div class="tree-category-label" style="height:32px; display:flex; align-items:center; cursor:pointer;" onclick="toggleVListCategory('${item.cat}')">
                                        <i class="bi bi-folder2-open" style="color:#94a3b8; margin-right:8px;"></i>
                                        ${item.cat}
                                        <i class="bi bi-chevron-${item.isOpen ? 'down' : 'right'} caret" style="margin-left:auto;"></i>
                                    </div>`;
                        } else {
                            const arch = item.arch;
                            const fpath = (arch.filepath || arch.filename).replace(/\\\\/g, '\\\\\\\\').replace(/'/g, "\\\\'");
                            const fname = arch.filename.replace(/'/g, "\\\\'");
                            return `<div class="tree-file" style="height:32px; padding-left:20px; display:flex; align-items:center; cursor:pointer;" onclick="selectRealFile('${casoId}', '${fpath}', '${fname}', '${arch.tipo}', ${arch.size_kb})">
                                        <i class="bi ${arch.icono} tree-file-icon" style="color:${arch.color}; margin-right:8px;"></i>
                                        <span style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:70%;">${arch.filename}</span>
                                        <span style="margin-left:auto; font-size:0.68rem; color:var(--text-muted);">${arch.size_kb} KB</span>
                                    </div>`;
                        }
                    }'''

new_render = '''                    renderItem: (item) => {
                        if (item.type === 'category') {
                            return '<div class="tree-category ' + (item.isOpen ? 'open' : '') + '" style="border-radius:0;">'
                                + '<div class="tree-category-label" onclick="toggleVListCategory(\\'' + item.cat.replace(/'/g, "\\\\'") + '\\')">'
                                + '<i class="bi bi-folder2-open"></i>'
                                + item.cat
                                + '<i class="bi bi-chevron-right caret"></i>'
                                + '</div></div>';
                        } else {
                            const arch = item.arch;
                            const fpath = (arch.filepath || arch.filename).replace(/\\\\/g, '\\\\\\\\').replace(/'/g, "\\\\'");
                            const fname = arch.filename.replace(/'/g, "\\\\'");
                            return '<div class="tree-file" onclick="selectRealFile(\\'' + casoId + '\\', \\'' + fpath + '\\', \\'' + fname + '\\', \\'' + arch.tipo + '\\', ' + arch.size_kb + ')">'
                                + '<i class="bi ' + arch.icono + ' tree-file-icon" style="color:' + arch.color + ';"></i>'
                                + '<span style="max-width:70%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">' + arch.filename + '</span>'
                                + '<span style="margin-left:auto; font-size:0.68rem; color:var(--text-muted);">' + arch.size_kb + ' KB</span>'
                                + '</div>';
                        }
                    }'''

if old_render in content:
    new_content = content.replace(old_render, new_render)
    with open('web_app/templates/index.html', 'w') as f:
        f.write(new_content)
    print("Replaced renderItem successfully.")
else:
    print("Pattern not found — check indentation or characters.")
    # Show what's at the relevant section
    idx = content.find('renderItem: (item) =>')
    print(f"Found renderItem at character {idx}")
    print(repr(content[idx:idx+200]))
