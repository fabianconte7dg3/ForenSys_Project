document.addEventListener('DOMContentLoaded', () => {

    // Telemetry logic has been moved to index.html

    // --- SPA Navigation Logic ---
    const navLinks = document.querySelectorAll('.nav-link');
    const sections = document.querySelectorAll('.content-section');
    const sectionTitle = document.getElementById('current-section-title');

    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            
            // Remove active classes from navigation
            navLinks.forEach(l => l.classList.remove('active'));
            // Add active class to clicked link
            e.currentTarget.classList.add('active');

            // Hide all sections
            sections.forEach(sec => {
                sec.classList.add('d-none');
                sec.classList.remove('active');
            });

            // Show target section
            const targetId = e.currentTarget.getAttribute('data-target');
            const targetElement = document.getElementById(targetId);
            if(targetElement) {
                targetElement.classList.remove('d-none');
                // Short timeout to allow display:block to apply before opacity transition
                setTimeout(() => {
                    targetElement.classList.add('active');
                }, 10);
            }

            // Update title
            sectionTitle.textContent = e.currentTarget.textContent.trim();
        });
    });

    const buttons = {
        wiping: document.getElementById('btn-wiping'),
        disk: document.getElementById('btn-disk'),
        usbRam: document.getElementById('btn-usb-ram'),
        ram: document.getElementById('btn-ram'),
        mobile: document.getElementById('btn-mobile'),
        cloud: document.getElementById('btn-cloud'),
        timeline: document.getElementById('btn-timeline'),
        ia: document.getElementById('btn-ia'),
        report: document.getElementById('btn-report')
    };
    
    const consoleBox = document.getElementById('live-log');
    const logStatus = document.getElementById('log-status');
    let logInterval = null;

    // --- Case Management Logic ---
    const caseForm = document.getElementById('case-form');
    if(caseForm) {
        const caseInputElements = caseForm.querySelectorAll('.form-control');
        const btnOpenCase = document.getElementById('btn-open-case');
        
        // Initially disable all operation buttons
        Object.values(buttons).forEach(btn => { if(btn) btn.disabled = true; });

        caseForm.addEventListener('submit', (e) => {
            e.preventDefault();
            
            // Save case info globally
            window.activeCaseInfo = {
                number: document.getElementById('case-number').value,
                name: document.getElementById('case-name').value,
                investigator: document.getElementById('investigator-name').value
            };

            // Lock form
            caseInputElements.forEach(input => input.setAttribute('readonly', 'true'));
            btnOpenCase.disabled = true;
            btnOpenCase.classList.replace('btn-outline-success', 'btn-secondary');
            btnOpenCase.innerHTML = '<i class="bi bi-lock-fill me-2"></i>Caso Abierto (Solo Lectura)';
            
            // Enable operation buttons
            Object.values(buttons).forEach(btn => { if(btn) btn.disabled = false; });
            
            // Auto switch to Operations tab
            document.querySelector('[data-target="operations"]').click();
        });
    }

    // Helper: Add line to log
    function addLogLine(message, type = 'info') {
        const line = document.createElement('div');
        line.className = `log-line ${type}`;
        
        const timestamp = document.createElement('span');
        timestamp.className = 'timestamp';
        const now = new Date();
        timestamp.textContent = `[${now.toTimeString().split(' ')[0]}.${now.getMilliseconds().toString().padStart(3, '0')}]`;
        
        const text = document.createElement('span');
        text.innerHTML = message;
        
        line.appendChild(timestamp);
        line.appendChild(text);
        
        consoleBox.appendChild(line);
        // Autoscroll
        consoleBox.scrollTop = consoleBox.scrollHeight;
    }

    // Mock progress generators
    function simulateProcess(processName, steps) {
        if(logInterval) clearInterval(logInterval);
        
        // Disable all buttons
        Object.values(buttons).forEach(btn => { if(btn) btn.disabled = true; });
        
        logStatus.textContent = "Running";
        logStatus.className = "badge bg-warning text-dark";

        if(window.activeCaseInfo && window.activeCaseInfo.number) {
            addLogLine(`[INFO] Iniciando tarea para el CASO: ${window.activeCaseInfo.number} - Perito: ${window.activeCaseInfo.investigator}`, 'warning');
        }
        addLogLine(`--- INITIATING ${processName} ---`, 'warning');
        
        let currentStep = 0;
        
        logInterval = setInterval(() => {
            if(currentStep < steps.length) {
                addLogLine(steps[currentStep].msg, steps[currentStep].type);
                currentStep++;
            } else {
                clearInterval(logInterval);
                addLogLine(`--- ${processName} COMPLETED SUCCESSFULLY ---`, 'success');
                
                // Re-enable all buttons
                Object.values(buttons).forEach(btn => { if(btn) btn.disabled = false; });
                
                logStatus.textContent = "Inactivo";
                logStatus.className = "badge bg-secondary";
            }
        }, 400); // 400ms per line
    }

    // --- PIPELINE TABS LOGIC ---
    const pipelineBtns = document.querySelectorAll('.pipe-btn');
    const modulePanels = document.querySelectorAll('.module-panel');
    const configContainer = document.getElementById('module-config-container');

    pipelineBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            // Remove active from all buttons
            pipelineBtns.forEach(b => {
                b.style.boxShadow = 'none';
                b.style.transform = 'translateY(0)';
                b.style.border = '1px solid transparent';
            });
            // Hide all panels
            modulePanels.forEach(p => p.style.display = 'none');
            
            // Activate clicked
            btn.style.boxShadow = 'var(--shadow-md)';
            btn.style.transform = 'translateY(-2px)';
            btn.style.border = '1px solid var(--border-dim)';
            
            // Show config container and specific panel
            configContainer.style.display = 'block';
            const op = btn.getAttribute('data-op');
            const panel = document.getElementById(`panel-${op}`);
            if(panel) {
                panel.style.display = 'block';
            }
        });
    });

    // --- EXECUTE BUTTONS LOGIC ---
    const runBtnWiping = document.getElementById('btn-run-wiping');
    if (runBtnWiping) runBtnWiping.addEventListener('click', () => {
        const wipeSteps = [
            { msg: "Mounting target drive...", type: "info" },
            { msg: "Starting Pass 1 (NIST 800-88 Clear)...", type: "info" },
            { msg: "Progress: 50% - 150MB/s", type: "success" },
            { msg: "NIST 800-88 Clear specification met.", type: "success" }
        ];
        simulateProcess("WIPING NIST 800-88", wipeSteps);
    });

    const runBtnDisk = document.getElementById('btn-run-disk');
    if (runBtnDisk) runBtnDisk.addEventListener('click', () => {
        const extractSteps = [
            { msg: "Initializing dc3dd (version 7.2)", type: "info" },
            { msg: "Read Error at sector 2048592 - Attempting zero fill", type: "error" },
            { msg: "Imaging complete. Computing hashes...", type: "info" },
            { msg: "Hash verification matched.", type: "success" }
        ];
        simulateProcess("DC3DD IMAGE EXTRACTION", extractSteps);
    });

    const runBtnCreator = document.getElementById('btn-run-creator');
    if (runBtnCreator) runBtnCreator.addEventListener('click', () => {
        const targetUsb = document.getElementById('usb-ram')?.value || '/dev/sdc';
        const steps = [
            { msg: `[INFO] Desactivando bloqueador de escritura forense para ${targetUsb}...`, type: "info" },
            { msg: "[PROGRESO] Reconstruyendo tabla de particiones...", type: "info" },
            { msg: "[ÉXITO] LIVE RESPONSE USB ESTÁ LISTO.", type: "success" }
        ];
        simulateProcess("CREADOR USB LIVE RAM", steps);
    });

    const runBtnRam = document.getElementById('btn-run-ram');
    if (runBtnRam) runBtnRam.addEventListener('click', () => {
        const ramPath = document.getElementById('ram-path')?.value || 'auto-detectado';
        const steps = [
            { msg: `[INFO] Iniciando análisis de memoria volátil. Archivo origen: ${ramPath}`, type: "info" },
            { msg: "[PROGRESO] Buscando inyecciones de código malicioso...", type: "warning" },
            { msg: "[ÉXITO] Archivos .txt están listos en la carpeta del caso.", type: "success" }
        ];
        simulateProcess("RAM EXTRACTION", steps);
    });

    const runBtnMobile = document.getElementById('btn-run-mobile');
    if (runBtnMobile) runBtnMobile.addEventListener('click', () => {
        const steps = [
            { msg: "[INFO] Verificando conexión y autorización del dispositivo móvil (ADB)...", type: "info" },
            { msg: "[ÉXITO] Toda la evidencia del celular reside segura en la bóveda.", type: "success" }
        ];
        simulateProcess("MOBILE (ADB) EXTRACTION", steps);
    });

    const runBtnCloud = document.getElementById('btn-run-cloud');
    if (runBtnCloud) runBtnCloud.addEventListener('click', () => {
        const targetUrl = document.getElementById('osint-url')?.value || 'https://instagram.com/...';
        const steps = [
            { msg: `[INFO] Desplegando rastreador fantasma. Objetivo: ${targetUrl}`, type: "info" },
            { msg: "[ÉXITO] Código fuente preservado en la bóveda.", type: "success" }
        ];
        simulateProcess("CLOUD CAPTURE (OSINT)", steps);
    });

    const runBtnTimeline = document.getElementById('btn-run-timeline');
    if (runBtnTimeline) runBtnTimeline.addEventListener('click', () => {
        // En lugar de iniciar inmediatamente, abrimos el explorador
        openExplorerModal('/');
    });

    const runBtnIa = document.getElementById('btn-run-ia');
    if (runBtnIa) runBtnIa.addEventListener('click', () => {
        const steps = [
            { msg: "[INFO] Conectando con servidor local Ollama (Modelo: gemma3:4b)...", type: "info" },
            { msg: "[ÉXITO] Dictamen Pericial generado en formato Markdown.", type: "success" }
        ];
        simulateProcess("AI FORENSIC TRIAGE", steps);
    });

    const runBtnReport = document.getElementById('btn-run-report');
    if (runBtnReport) runBtnReport.addEventListener('click', () => {
        const steps = [
            { msg: "[INFO] Convirtiendo Dictamen Pericial a formato PDF con formato institucional...", type: "info" },
            { msg: "[ÉXITO] Reporte pericial en PDF generado correctamente.", type: "success" }
        ];
        simulateProcess("PDF EXPORT", steps);
    });

    // --- EXPLORER MODAL LOGIC ---
    let selectedEvidencePath = null;
    const explorerModal = document.getElementById('explorer-modal');
    const explorerItems = document.getElementById('explorer-items');
    const explorerPathLabel = document.getElementById('explorer-current-path');
    
    window.closeExplorerModal = function() {
        if(explorerModal) explorerModal.classList.remove('open');
    };

    function openExplorerModal(path) {
        if(!explorerModal) return;
        
        fetch('/api/explore', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: path })
        })
        .then(res => res.json())
        .then(data => {
            if(data.status === 'success') {
                explorerPathLabel.textContent = data.current_path;
                explorerItems.innerHTML = '';
                
                // Botón Atrás si no estamos en la raíz
                if(data.current_path !== '/') {
                    const backItem = document.createElement('div');
                    backItem.className = 'tree-file';
                    backItem.innerHTML = '<i class="bi bi-arrow-up-left-square-fill me-2" style="color:var(--accent-blue);"></i>.. (Atrás)';
                    backItem.style.cursor = 'pointer';
                    backItem.onclick = () => openExplorerModal(data.parent_path);
                    explorerItems.appendChild(backItem);
                }
                
                data.items.forEach(item => {
                    const el = document.createElement('div');
                    el.className = 'tree-file';
                    el.style.cursor = 'pointer';
                    el.style.padding = '5px';
                    el.style.borderBottom = '1px solid var(--border-dim)';
                    
                    if(item.is_dir) {
                        el.innerHTML = `<i class="bi bi-folder-fill me-2" style="color:var(--accent-blue);"></i>${item.name}`;
                        el.onclick = () => openExplorerModal(item.path);
                    } else {
                        el.innerHTML = `<i class="bi bi-file-earmark-fill me-2" style="color:var(--text-muted);"></i>${item.name}`;
                        el.onclick = () => {
                            // Marcar como seleccionado
                            Array.from(explorerItems.children).forEach(c => c.style.background = 'transparent');
                            el.style.background = 'rgba(59,130,246,.2)';
                            selectedEvidencePath = item.path;
                        };
                    }
                    explorerItems.appendChild(el);
                });
                
                explorerModal.classList.add('open');
            } else {
                alert("Error al cargar ruta: " + data.message);
            }
        })
        .catch(err => console.error(err));
    }

    const btnConfirmExplorer = document.getElementById('btn-confirm-explorer');
    if(btnConfirmExplorer) {
        btnConfirmExplorer.addEventListener('click', () => {
            if(!selectedEvidencePath) {
                alert("Por favor selecciona un archivo de evidencia.");
                return;
            }
            // Empaquetar y enviar a Flask
            const casoId = window.activeCaseInfo ? window.activeCaseInfo.number : (window.activeCaseNumber || 'CASO_DEFAULT');
            
            closeExplorerModal();
            addLogLine(`[SISTEMA] Iniciando Normalización Forense...`, 'info');
            addLogLine(`[INFO] Caso: ${casoId} | Evidencia: ${selectedEvidencePath}`, 'warning');
            logStatus.textContent = "Running";
            logStatus.className = "badge bg-warning text-dark";
            
            fetch('/api/run/timeline', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    caso_id: casoId,
                    ruta_evidencia: selectedEvidencePath
                })
            })
            .then(res => res.json())
            .then(data => {
                if(data.status === 'success') {
                    addLogLine(`[ÉXITO] ${data.message}`, 'success');
                } else {
                    addLogLine(`[ERROR] ${data.message}`, 'error');
                }
                logStatus.textContent = "Inactivo";
                logStatus.className = "badge bg-secondary";
            })
            .catch(err => {
                addLogLine(`[ERROR] Fallo de conexión: ${err}`, 'error');
                logStatus.textContent = "Error";
                logStatus.className = "badge bg-danger";
            });
        });
    }

    if (buttons.ia) buttons.ia.addEventListener('click', () => {
        const steps = [
            { msg: "[INFO] Conectando con servidor local Ollama (Modelo: gemma3:4b)...", type: "info" },
            { msg: "[PROGRESO] Recopilando inteligencia de los 9 módulos de evidencia extraídos...", type: "info" },
            { msg: "[PROGRESO] Evaluando artefactos mediante sistema de RAG y Presupuesto de Tokens...", type: "warning" },
            { msg: "[PROGRESO] Analizando con IA (Generando Dictamen Pericial)...", type: "info" },
            { msg: "[ÉXITO] Dictamen Pericial generado en formato Markdown.", type: "success" }
        ];
        simulateProcess("AI FORENSIC TRIAGE", steps);
    });

    if (buttons.report) buttons.report.addEventListener('click', () => {
        const steps = [
            { msg: "[INFO] Convirtiendo Dictamen Pericial a formato PDF con formato institucional...", type: "info" },
            { msg: "[INFO] Consolidando cadena de custodia y Hashes SHA-256...", type: "warning" },
            { msg: "[PROGRESO] Procesando tablas y alertas de severidad (Rojo/Amarillo/Verde)...", type: "info" },
            { msg: "[ÉXITO] Reporte pericial en PDF generado correctamente.", type: "success" }
        ];
        simulateProcess("PDF EXPORT", steps);
    });

});
