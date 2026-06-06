import re

with open('web_app/templates/index.html', 'r') as f:
    content = f.read()

pattern = r'function loadRealEvidence\(casoId\).*?}\n}'
replacement = '''function loadRealEvidence(casoId) {
    const statusLabel = document.getElementById('evidence-status-label');
    const dynTree     = document.getElementById('evidence-tree-dynamic');
    const staticTree  = document.getElementById('evidence-tree-static');

    if (!casoId) {
        if (statusLabel) statusLabel.textContent = 'No hay caso activo. Abre o importa un caso primero.';
        return;
    }
    if (statusLabel) statusLabel.textContent = 'Cargando archivos...';
    if (staticTree) staticTree.style.display = 'none';

    // VirtualList needs to be created if not exists
    let vList = document.querySelector('forensys-virtual-list#evidence-vlist');
    if (!vList) {
        vList = document.createElement('forensys-virtual-list');
        vList.id = 'evidence-vlist';
        dynTree.innerHTML = '';
        dynTree.appendChild(vList);
    }

    fetch(`/api/case/${casoId}/results`)
        .then(r => r.json())
        .then(data => {
            if (!data.archivos || data.archivos.length === 0) {
                if (statusLabel) statusLabel.textContent = '⚠ No se encontraron archivos. ¿Está conectado el disco externo y se ejecutó el Módulo 7?';
                vList.config = { items: [], renderItem: () => '' };
                return;
            }

            // Flatten data into a list for virtualization
            const flattened = [];
            const categorias = {};
            data.archivos.forEach(arch => {
                if (!categorias[arch.categoria]) categorias[arch.categoria] = [];
                categorias[arch.categoria].push(arch);
            });

            // Store category toggles locally (default open)
            window._vListToggleState = window._vListToggleState || {};

            window.toggleVListCategory = function(cat) {
                window._vListToggleState[cat] = !window._vListToggleState[cat];
                rebuildVList();
            };

            const rebuildVList = () => {
                const flatItems = [];
                Object.keys(categorias).forEach(cat => {
                    const isOpen = window._vListToggleState[cat] !== false;
                    flatItems.push({ type: 'category', cat, isOpen });
                    if (isOpen) {
                        categorias[cat].forEach(arch => {
                            flatItems.push({ type: 'file', arch });
                        });
                    }
                });

                vList.config = {
                    items: flatItems,
                    itemHeight: 32,
                    renderItem: (item) => {
                        if (item.type === 'category') {
                            return `<div class="tree-category-label" style="height:32px; display:flex; align-items:center; cursor:pointer;" onclick="toggleVListCategory('${item.cat}')">
                                        <i class="bi bi-folder2-open" style="color:#94a3b8; margin-right:8px;"></i>
                                        ${item.cat}
                                        <i class="bi bi-chevron-${item.isOpen ? 'down' : 'right'} caret" style="margin-left:auto;"></i>
                                    </div>`;
                        } else {
                            const arch = item.arch;
                            const fpath = (arch.filepath || arch.filename).replace(/\\/g, '\\\\').replace(/'/g, "\\\\'");
                            const fname = arch.filename.replace(/'/g, "\\\\'");
                            return `<div class="tree-file" style="height:32px; padding-left:20px; display:flex; align-items:center; cursor:pointer;" onclick="selectRealFile('${casoId}', '${fpath}', '${fname}', '${arch.tipo}', ${arch.size_kb})">
                                        <i class="bi ${arch.icono} tree-file-icon" style="color:${arch.color}; margin-right:8px;"></i>
                                        <span style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:70%;">${arch.filename}</span>
                                        <span style="margin-left:auto; font-size:0.68rem; color:var(--text-muted);">${arch.size_kb} KB</span>
                                    </div>`;
                        }
                    }
                };
            };

            rebuildVList();
            if (statusLabel) statusLabel.textContent = `✓ ${data.archivos.length} archivos cargados.`;
        })
        .catch(err => {
            console.error('Error fetching real evidence:', err);
            if (statusLabel) statusLabel.textContent = 'Error al cargar evidencia real.';
        });
}'''

new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
with open('web_app/templates/index.html', 'w') as f:
    f.write(new_content)
