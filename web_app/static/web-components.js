// web-components.js
// Colección de componentes nativos Web Component (Custom Elements v1) para ForenSys

class ForensysProgress extends HTMLElement {
    constructor() {
        super();
        this.attachShadow({ mode: 'open' });
        this.shadowRoot.innerHTML = `
            <style>
                :host {
                    display: block;
                    width: 100%;
                    font-family: var(--font-primary, system-ui, sans-serif);
                }
                .progress-container {
                    background: rgba(15, 23, 42, 0.6);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 6px;
                    padding: 12px;
                    margin-top: 15px;
                }
                .progress-header {
                    display: flex;
                    justify-content: space-between;
                    margin-bottom: 8px;
                    font-size: 0.85rem;
                }
                .progress-title {
                    color: var(--text-primary, #f8fafc);
                    font-weight: 600;
                }
                .progress-pct {
                    color: var(--accent-cyan, #06b6d4);
                    font-weight: 700;
                    font-variant-numeric: tabular-nums;
                }
                .progress-bar-bg {
                    width: 100%;
                    height: 8px;
                    background: rgba(255, 255, 255, 0.05);
                    border-radius: 4px;
                    overflow: hidden;
                    position: relative;
                }
                .progress-bar-fill {
                    height: 100%;
                    background: var(--progress-color, var(--accent-cyan, #06b6d4));
                    width: 0%;
                    transition: width 0.4s cubic-bezier(0.4, 0, 0.2, 1);
                }
                .progress-detail {
                    margin-top: 8px;
                    font-size: 0.75rem;
                    color: var(--text-muted, #94a3b8);
                    white-space: nowrap;
                    overflow: hidden;
                    text-overflow: ellipsis;
                }
            </style>
            <div class="progress-container">
                <div class="progress-header">
                    <span class="progress-title" id="title"><slot name="title">Operación en curso</slot></span>
                    <span class="progress-pct" id="pct">0%</span>
                </div>
                <div class="progress-bar-bg">
                    <div class="progress-bar-fill" id="bar"></div>
                </div>
                <div class="progress-detail" id="detail"><slot name="detail">Iniciando...</slot></div>
            </div>
        `;
    }

    static get observedAttributes() {
        return ['value', 'color'];
    }

    attributeChangedCallback(name, oldValue, newValue) {
        if (name === 'value') {
            const pct = Math.max(0, Math.min(100, parseInt(newValue) || 0));
            this.shadowRoot.getElementById('bar').style.width = pct + '%';
            this.shadowRoot.getElementById('pct').textContent = pct + '%';
        } else if (name === 'color') {
            this.style.setProperty('--progress-color', newValue);
        }
    }

    set detail(text) {
        this.shadowRoot.getElementById('detail').textContent = text;
    }
}

class ForensysTerminal extends HTMLElement {
    constructor() {
        super();
        this.attachShadow({ mode: 'open' });
        this.shadowRoot.innerHTML = `
            <style>
                :host {
                    display: block;
                    width: 100%;
                    height: 100%;
                }
                .terminal-container {
                    background-color: var(--bg-surface, #0f172a);
                    border-radius: 6px;
                    border: 1px solid var(--border-color, rgba(255,255,255,0.05));
                    padding: 16px;
                    font-family: var(--font-mono, monospace);
                    font-size: 0.82rem;
                    color: var(--text-muted, #cbd5e1);
                    height: calc(100% - 32px);
                    overflow-y: auto;
                    display: flex;
                    flex-direction: column;
                }
                .terminal-container::-webkit-scrollbar {
                    width: 6px;
                }
                .terminal-container::-webkit-scrollbar-thumb {
                    background: rgba(255,255,255,0.2);
                    border-radius: 3px;
                }
                .log-line {
                    margin: 2px 0;
                    line-height: 1.4;
                    word-wrap: break-word;
                }
                .log-error { color: #f87171; }
                .log-warn { color: #fbbf24; }
                .log-success { color: #34d399; }
                .log-system { color: #60a5fa; }
                .log-cmd { color: #a78bfa; font-weight: bold; }
                
                .terminal-header {
                    display: flex;
                    align-items: center;
                    margin-bottom: 12px;
                    padding-bottom: 8px;
                    border-bottom: 1px dashed rgba(255,255,255,0.1);
                }
                .terminal-dot {
                    width: 10px; height: 10px; border-radius: 50%;
                    margin-right: 6px;
                }
                .dot-red { background: #ef4444; }
                .dot-yellow { background: #eab308; }
                .dot-green { background: #22c55e; }
            </style>
            <div class="terminal-container" id="container">
                <div class="terminal-header" id="header" style="display:none;">
                    <div class="terminal-dot dot-red"></div>
                    <div class="terminal-dot dot-yellow"></div>
                    <div class="terminal-dot dot-green"></div>
                    <span style="margin-left: 10px; opacity: 0.7;">Terminal de Logs</span>
                </div>
                <div id="logs-area">
                    <slot></slot>
                </div>
            </div>
        `;
        this.container = this.shadowRoot.getElementById('container');
        this.logsArea = this.shadowRoot.getElementById('logs-area');
    }

    connectedCallback() {
        if (this.hasAttribute('show-header')) {
            this.shadowRoot.getElementById('header').style.display = 'flex';
        }
    }

    addLog(text, type = 'log-normal') {
        const line = document.createElement('div');
        line.className = 'log-line ' + type;
        
        // Auto-detect types if not explicitly provided
        if (type === 'log-normal') {
            if (text.includes('[ERROR]') || text.includes('[X]')) line.classList.add('log-error');
            else if (text.includes('[WARN]') || text.includes('[!]')) line.classList.add('log-warn');
            else if (text.includes('[SUCCESS]') || text.includes('[+]') || text.includes('[✓]')) line.classList.add('log-success');
            else if (text.includes('[SISTEMA]') || text.includes('[*]')) line.classList.add('log-system');
        }

        line.textContent = text;
        this.logsArea.appendChild(line);
        this.autoScroll();
    }

    clear() {
        this.logsArea.innerHTML = '';
    }

    autoScroll() {
        // Debounce slightly to prevent thrashing
        if (this._scrollTimeout) clearTimeout(this._scrollTimeout);
        this._scrollTimeout = setTimeout(() => {
            this.container.scrollTop = this.container.scrollHeight;
        }, 50);
    }
}

customElements.define('forensys-progress', ForensysProgress);
customElements.define('forensys-terminal', ForensysTerminal);

class ForensysVirtualList extends HTMLElement {
    constructor() {
        super();
        this.attachShadow({ mode: 'open' });
        this.items = [];
        this.itemHeight = 35;
        this.renderItem = (item) => `<div>${item}</div>`;
        this.buffer = 10;

        this.shadowRoot.innerHTML = `
            <style>
                :host {
                    display: block;
                    width: 100%;
                    height: 100%;
                    overflow-y: auto;
                    position: relative;
                }
                .virtual-scroll-spacer {
                    width: 1px;
                }
                .virtual-list-content {
                    position: absolute;
                    top: 0;
                    left: 0;
                    width: 100%;
                }
            </style>
            <div class="virtual-scroll-spacer" id="spacer"></div>
            <div class="virtual-list-content" id="content"></div>
        `;
        
        this.spacer = this.shadowRoot.getElementById('spacer');
        this.content = this.shadowRoot.getElementById('content');
        
        // Using scroll event is the most robust way for pure 50-line virtualization
        // IntersectionObserver can be used on sentinels, but scroll is simpler and zero lag.
        this.addEventListener('scroll', () => this.updateRender(), { passive: true });
    }

    set config({ items, renderItem, itemHeight = 35 }) {
        this.items = items;
        this.renderItem = renderItem;
        this.itemHeight = itemHeight;
        this.spacer.style.height = (this.items.length * this.itemHeight) + 'px';
        this.updateRender();
    }

    updateRender() {
        if (!this.items.length) {
            this.content.innerHTML = '';
            return;
        }
        
        const scrollTop = this.scrollTop;
        const viewportHeight = this.clientHeight;
        
        const startIndex = Math.max(0, Math.floor(scrollTop / this.itemHeight) - this.buffer);
        const visibleCount = Math.ceil(viewportHeight / this.itemHeight) + (this.buffer * 2);
        const endIndex = Math.min(this.items.length - 1, startIndex + visibleCount);
        
        const visibleItems = this.items.slice(startIndex, endIndex + 1);
        
        let html = '';
        visibleItems.forEach(item => {
            html += this.renderItem(item);
        });
        
        this.content.innerHTML = html;
        this.content.style.transform = `translateY(${startIndex * this.itemHeight}px)`;
    }
}

customElements.define('forensys-virtual-list', ForensysVirtualList);
