/* Code Param Tuner — Frontend App */

// ── State ──
let sourceEditor = null;
let outputEditor = null;
let sourceCode = '';
let params = [];
let allParams = [];
let modifiedValues = {};
let decorations = [];
let updateTimer = null;
let inlineInputSeq = 0;
let codeSections = [];
let codeReviewScrollHandler = null;
let sidePanelsCollapsed = { source: false, output: false };

// ── Theme ──
const THEME_KEY = 'cpt_theme';

function getCurrentTheme() {
    return localStorage.getItem(THEME_KEY) === 'light' ? 'light' : 'dark';
}

function monacoThemeName(theme) {
    return theme === 'light' ? 'vs' : 'vs-dark';
}

function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    const btn = document.getElementById('btnTheme');
    if (btn) {
        btn.textContent = theme === 'light' ? '暗色' : '浅色';
        btn.setAttribute('aria-pressed', String(theme === 'light'));
    }
    if (window.monaco?.editor) {
        monaco.editor.setTheme(monacoThemeName(theme));
    }
}

applyTheme(getCurrentTheme());

// ── Monaco Loader ──
require.config({ paths: { vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs' } });
require(['vs/editor/editor.main'], function () {
    const editorTheme = monacoThemeName(getCurrentTheme());
    const commonOpts = {
        language: 'python',
        theme: editorTheme,
        minimap: { enabled: false },
        fontSize: 13,
        fontFamily: '"SF Mono", "Fira Code", "JetBrains Mono", Menlo, monospace',
        lineNumbers: 'on',
        scrollBeyondLastLine: false,
        automaticLayout: true,
        wordWrap: 'on',
        padding: { top: 12 },
        renderLineHighlight: 'gutter',
        smoothScrolling: true,
        cursorSmoothCaretAnimation: 'on',
    };

    sourceEditor = monaco.editor.create(document.getElementById('editorSource'), {
        ...commonOpts,
        value: '',
        readOnly: false,
    });

    // M4: outputEditor set to readOnly
    outputEditor = monaco.editor.create(document.getElementById('editorOutput'), {
        ...commonOpts,
        value: '',
        readOnly: true,
    });

    sourceEditor.onDidChangeModelContent(() => {
        const hasCode = sourceEditor.getValue().trim() !== '';
        document.getElementById('btnAnalyze').disabled = !hasCode;
    });
});

document.getElementById('btnTheme').addEventListener('click', () => {
    const nextTheme = getCurrentTheme() === 'light' ? 'dark' : 'light';
    localStorage.setItem(THEME_KEY, nextTheme);
    applyTheme(nextTheme);
});

// ── Panel Visibility ──
function setSidePanelCollapsed(which, collapsed) {
    sidePanelsCollapsed[which] = collapsed;
    const sourceCollapsed = sidePanelsCollapsed.source;
    const outputCollapsed = sidePanelsCollapsed.output;
    const panel2 = document.getElementById('panel2');

    document.body.classList.toggle('source-collapsed', sourceCollapsed);
    document.body.classList.toggle('output-collapsed', outputCollapsed);
    panel2.style.flex = (sourceCollapsed || outputCollapsed) ? '1 1 100%' : '';
    panel2.style.minWidth = (sourceCollapsed || outputCollapsed) ? '0' : '';

    document.getElementById('btnToggleSource').textContent = sourceCollapsed ? '显示源代码' : '隐藏源代码';
    document.getElementById('btnToggleOutput').textContent = outputCollapsed ? '显示输出' : '隐藏输出';
    document.getElementById('btnFocusMode').textContent = (sourceCollapsed && outputCollapsed) ? '退出专注' : '专注模式';

    requestAnimationFrame(() => {
        sourceEditor?.layout();
        outputEditor?.layout();
    });
}

document.getElementById('btnToggleSource').addEventListener('click', () => {
    setSidePanelCollapsed('source', !sidePanelsCollapsed.source);
});
document.getElementById('btnCollapseSource').addEventListener('click', () => {
    setSidePanelCollapsed('source', true);
});
document.getElementById('btnToggleOutput').addEventListener('click', () => {
    setSidePanelCollapsed('output', !sidePanelsCollapsed.output);
});
document.getElementById('btnCollapseOutput').addEventListener('click', () => {
    setSidePanelCollapsed('output', true);
});
document.getElementById('btnFocusMode').addEventListener('click', () => {
    const enteringFocus = !(sidePanelsCollapsed.source && sidePanelsCollapsed.output);
    setSidePanelCollapsed('source', enteringFocus);
    setSidePanelCollapsed('output', enteringFocus);
    document.getElementById('btnFocusMode').textContent = enteringFocus ? '退出专注' : '专注模式';
});

// ── Settings ──
const LEGACY_SETTING_KEYS = ['cpt_api_key', 'cpt_base_url', 'cpt_api_format', 'cpt_model'];
let cachedSettings = {
    hasApiKey: false,
    baseUrl: '',
    apiFormat: 'auto',
    model: '',
};

function normalizeSettings(data) {
    return {
        hasApiKey: Boolean(data?.has_api_key),
        baseUrl: data?.base_url || '',
        apiFormat: data?.api_format || 'auto',
        model: data?.model || '',
    };
}

async function loadSettings() {
    const resp = await fetch('/api/settings');
    if (!resp.ok) {
        throw new Error(`读取设置失败 HTTP ${resp.status}`);
    }
    cachedSettings = normalizeSettings(await resp.json());
    return cachedSettings;
}

async function saveSettings(s) {
    const resp = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            api_key: s.apiKey || undefined,
            clear_api_key: Boolean(s.clearApiKey),
            base_url: s.baseUrl ?? '',
            api_format: s.apiFormat || 'auto',
            model: s.model ?? '',
        }),
    });
    if (!resp.ok) {
        const text = await resp.text();
        throw new Error(`保存设置失败 HTTP ${resp.status}: ${text}`);
    }
    cachedSettings = normalizeSettings(await resp.json());
    LEGACY_SETTING_KEYS.forEach(key => localStorage.removeItem(key));
    return cachedSettings;
}

async function migrateLegacySettings() {
    const legacy = {
        apiKey: localStorage.getItem('cpt_api_key') || '',
        baseUrl: localStorage.getItem('cpt_base_url') || '',
        apiFormat: localStorage.getItem('cpt_api_format') || '',
        model: localStorage.getItem('cpt_model') || '',
    };
    const hasLegacySettings = Object.values(legacy).some(Boolean);
    if (!hasLegacySettings) return;

    try {
        await saveSettings({
            apiKey: legacy.apiKey,
            baseUrl: legacy.baseUrl,
            apiFormat: legacy.apiFormat || 'auto',
            model: legacy.model,
        });
    } finally {
        LEGACY_SETTING_KEYS.forEach(key => localStorage.removeItem(key));
    }
}

migrateLegacySettings().catch(err => console.warn('Legacy settings migration failed:', err));

// ── API ──
const ANALYZE_TIMEOUT_MS = 240_000;

async function analyzeCode(code, filename = '') {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), ANALYZE_TIMEOUT_MS);

    let resp;
    try {
        resp = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            signal: controller.signal,
            body: JSON.stringify({
                code,
                filename: filename || undefined,
            }),
        });
    } catch (err) {
        if (err.name === 'AbortError') {
            throw new Error('AI 审查超时，请稍后重试或直接使用基础模式结果');
        }
        throw err;
    } finally {
        clearTimeout(timeoutId);
    }

    if (!resp.ok) {
        const text = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${text}`);
    }
    return resp.json();
}

// ── File Import ──
document.getElementById('fileInput').addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (!file) return;
    // Frontend size check: 500KB
    if (file.size > 500_000) {
        alert(`文件过大（${(file.size / 1000).toFixed(0)}KB），最大支持 500KB`);
        e.target.value = '';
        return;
    }
    const reader = new FileReader();
    reader.onload = () => {
        try {
            const code = file.name.toLowerCase().endsWith('.ipynb')
                ? notebookToPython(String(reader.result))
                : String(reader.result);
            sourceEditor.setValue(code);
            document.getElementById('btnAnalyze').disabled = code.trim() === '';
        } catch (err) {
            alert('无法读取 notebook: ' + err.message);
        }
    };
    reader.readAsText(file);
    e.target.value = '';
});

// ── Paste ──
document.getElementById('btnPaste').addEventListener('click', async () => {
    try {
        const text = await navigator.clipboard.readText();
        sourceEditor.setValue(text);
        document.getElementById('btnAnalyze').disabled = text.trim() === '';
    } catch {
        alert('无法读取剪贴板，请直接在编辑器中粘贴 (Ctrl/Cmd+V)');
    }
});

// ── Analyze ──
document.getElementById('btnAnalyze').addEventListener('click', async () => {
    const code = sourceEditor.getValue();
    if (!code.trim()) return;

    const btn = document.getElementById('btnAnalyze');
    btn.disabled = true;
    btn.innerHTML = '<span class="loading-spinner"></span>分析中...';

    try {
        const result = await analyzeCode(code);
        sourceCode = code;

        const banner = document.getElementById('fallbackBanner');
        if (result.fallback) {
            banner.style.display = 'flex';
            const reason = result.error || '未配置 API';
            const suffix = reason.includes('已使用基础模式') ? '' : '，已使用基础模式';
            document.getElementById('fallbackText').textContent = `AI 分析不可用（${reason}）${suffix}。`;
        } else {
            banner.style.display = 'none';
        }

        allParams = result.params;
        codeSections = normalizeClientSections(result.sections, sourceCode);
        if (result.params.length === 0) {
            params = [];
            modifiedValues = {};
            showEditPhase();
        } else {
            showConfirmPhase();
        }
    } catch (err) {
        alert('分析失败: ' + err.message);
    } finally {
        btn.disabled = false;
        btn.textContent = '分析参数';
    }
});

// ── Confirm Phase ──
function showConfirmPhase() {
    document.getElementById('confirmPhase').style.display = 'block';
    document.getElementById('confirmEmpty').style.display = 'none';
    document.getElementById('confirmList').style.display = 'block';
    document.getElementById('editPhase').style.display = 'none';
    document.getElementById('btnBackToConfirm').style.display = 'none';

    const container = document.getElementById('confirmItems');
    container.innerHTML = '';

    allParams.forEach((p, i) => {
        const item = document.createElement('div');
        item.className = 'confirm-item';
        const conf = p.confidence || 0.5;
        const confClass = conf >= 0.7 ? 'confidence-high' : 'confidence-low';
        const desc = p.description || p.presetDesc || p.name;
        const groupBadge = p.group ? `<span class="confirm-item-group">${escHtml(p.group)}</span>` : '';

        item.innerHTML = `
            <input type="checkbox" data-idx="${i}" checked>
            <div class="confirm-item-info">
                <div class="confirm-item-name">${escHtml(p.name)}</div>
                <div class="confirm-item-desc">${escHtml(desc)}</div>
                <div class="confirm-item-meta">
                    <code>${escHtml(formatValue(p.value))}</code>
                    <span class="confirm-item-confidence ${confClass}">${Math.round(conf * 100)}%</span>
                    ${groupBadge}
                </div>
            </div>
        `;
        container.appendChild(item);
    });

    document.getElementById('selectAll').checked = true;
    document.getElementById('selectAll').onchange = (e) => {
        container.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = e.target.checked);
    };
}

document.getElementById('btnConfirm').addEventListener('click', () => {
    const checkboxes = document.querySelectorAll('#confirmItems input[type="checkbox"]');
    const selected = [];
    checkboxes.forEach(cb => {
        if (cb.checked) selected.push(allParams[parseInt(cb.dataset.idx)]);
    });
    params = selected;
    modifiedValues = {};
    showEditPhase();
});

document.getElementById('btnBackToConfirm').addEventListener('click', showConfirmPhase);

// ── Edit Phase ──
function showEditPhase() {
    document.getElementById('confirmPhase').style.display = 'none';
    document.getElementById('confirmList').style.display = 'none';
    document.getElementById('confirmEmpty').style.display = 'none';
    document.getElementById('editPhase').style.display = 'block';
    document.getElementById('btnBackToConfirm').style.display = 'inline-block';
    document.getElementById('btnResetAll').style.display = 'inline-block';
    document.getElementById('btnExport').disabled = false;

    renderCodeReview();
    updateOutputCode();
}

function renderCodeReview() {
    inlineInputSeq = 0;
    const container = document.getElementById('paramGroups');
    container.innerHTML = '';
    container.className = 'code-review';

    const paramsByLine = groupInlineParamsByLine(params);
    const sourceLines = sourceCode.split('\n');
    const sections = normalizeClientSections(codeSections, sourceCode);

    const stickyPane = document.createElement('div');
    stickyPane.className = 'section-sticky-pane';
    stickyPane.innerHTML = `
        <div class="section-sticky-head">
            <div>
                <div class="section-title"></div>
                <div class="section-lines"></div>
            </div>
            <button type="button" class="section-collapse-btn">收起</button>
        </div>
        <p></p>
    `;
    container.appendChild(stickyPane);

    sections.forEach(section => {
        const block = document.createElement('section');
        block.className = 'code-section';
        block.dataset.title = section.title;
        block.dataset.lines = `第 ${section.start_line}–${section.end_line} 行`;
        block.dataset.explanation = section.explanation;

        const codeBlock = document.createElement('div');
        codeBlock.className = 'section-code';
        for (let lineNo = section.start_line; lineNo <= section.end_line; lineNo++) {
            const line = sourceLines[lineNo - 1] ?? '';
            const lineParams = paramsByLine.get(lineNo) || [];
            const row = document.createElement('div');
            row.className = `code-row ${lineParams.length ? 'has-param' : ''}`;
            row.dataset.line = String(lineNo);

            const gutter = document.createElement('span');
            gutter.className = 'code-line-no';
            gutter.textContent = String(lineNo);
            row.appendChild(gutter);

            const codeText = document.createElement('div');
            codeText.className = 'code-text';
            appendCodeLineParts(codeText, line, lineParams);
            row.appendChild(codeText);
            codeBlock.appendChild(row);
        }
        block.appendChild(codeBlock);
        container.appendChild(block);
    });

    bindInlineControls(container);
    bindStickySectionPane(container, stickyPane);
    syncInlineModifiedState();
}

function bindStickySectionPane(container, stickyPane) {
    const panel = document.getElementById('editPhase');
    const sectionEls = Array.from(container.querySelectorAll('.code-section'));
    const collapseBtn = stickyPane.querySelector('.section-collapse-btn');
    if (codeReviewScrollHandler) {
        panel.removeEventListener('scroll', codeReviewScrollHandler);
        codeReviewScrollHandler = null;
    }

    const updateStickyPane = () => {
        if (!sectionEls.length) return;
        const panelTop = panel.getBoundingClientRect().top;
        const anchor = panelTop + stickyPane.offsetHeight + 10;
        let active = sectionEls[0];

        for (const sectionEl of sectionEls) {
            const rect = sectionEl.getBoundingClientRect();
            if (rect.top <= anchor && rect.bottom > panelTop) {
                active = sectionEl;
            }
        }

        stickyPane.querySelector('.section-title').textContent = active.dataset.title || '代码片段';
        stickyPane.querySelector('.section-lines').textContent = active.dataset.lines || '';
        stickyPane.querySelector('p').textContent = active.dataset.explanation || '';
    };

    codeReviewScrollHandler = updateStickyPane;
    panel.addEventListener('scroll', codeReviewScrollHandler, { passive: true });
    collapseBtn.addEventListener('click', () => {
        const collapsed = stickyPane.classList.toggle('collapsed');
        collapseBtn.textContent = collapsed ? '展开' : '收起';
    });
    updateStickyPane();
}

function groupInlineParamsByLine(selectedParams) {
    const byLine = new Map();
    selectedParams
        .filter(p => p.line === p.endLine)
        .slice()
        .sort((a, b) => a.line - b.line || a.col - b.col || b.endCol - a.endCol)
        .forEach(p => {
            const list = byLine.get(p.line) || [];
            const overlaps = list.some(existing => rangesOverlap(p.col, p.endCol, existing.col, existing.endCol));
            if (!overlaps) {
                list.push(p);
                byLine.set(p.line, list);
            }
        });
    byLine.forEach(list => list.sort((a, b) => a.col - b.col));
    return byLine;
}

function rangesOverlap(aStart, aEnd, bStart, bEnd) {
    return Math.max(aStart, bStart) < Math.min(aEnd, bEnd);
}

function appendCodeLineParts(target, line, lineParams) {
    let cursor = 0;
    lineParams.forEach(p => {
        if (p.col > cursor) appendCodeText(target, line.slice(cursor, p.col));
        target.appendChild(createInlineControl(p));
        cursor = Math.max(cursor, p.endCol);
    });
    appendCodeText(target, line.slice(cursor) || '\u00a0');
}

function appendCodeText(target, text) {
    appendHighlightedCode(target, text);
}

function appendHighlightedCode(target, text) {
    if (!text) return;
    const tokenPattern = /(#.*$)|("""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|\b(False|None|True|and|as|assert|async|await|break|class|continue|def|del|elif|else|except|finally|for|from|global|if|import|in|is|lambda|nonlocal|not|or|pass|raise|return|try|while|with|yield)\b|\b(\d+(?:\.\d+)?(?:e[+-]?\d+)?)\b|([A-Za-z_]\w*)(?=\s*\()/gi;
    let lastIndex = 0;
    let match;

    while ((match = tokenPattern.exec(text)) !== null) {
        if (match.index > lastIndex) {
            appendToken(target, 'code-fixed', text.slice(lastIndex, match.index));
        }

        const value = match[0];
        if (match[1]) {
            appendToken(target, 'code-comment', value);
        } else if (match[2]) {
            appendToken(target, 'code-string', value);
        } else if (match[3]) {
            appendToken(target, 'code-keyword', value);
        } else if (match[4]) {
            appendToken(target, 'code-number', value);
        } else if (match[5]) {
            appendToken(target, 'code-call', value);
        } else {
            appendToken(target, 'code-fixed', value);
        }
        lastIndex = tokenPattern.lastIndex;
    }

    if (lastIndex < text.length) {
        appendToken(target, 'code-fixed', text.slice(lastIndex));
    }
}

function appendToken(target, className, text) {
    const span = document.createElement('span');
    span.className = className;
    span.textContent = text;
    target.appendChild(span);
}

function createInlineControl(p) {
    const wrapper = document.createElement('span');
    wrapper.className = 'inline-param';
    wrapper.dataset.paramId = p.id;
    wrapper.title = inlineParamTitle(p);

    const currentValue = modifiedValues[p.id] !== undefined ? modifiedValues[p.id] : p.value;

    if (p.type === 'bool') {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'inline-toggle';
        btn.dataset.paramId = p.id;
        btn.textContent = formatValue(currentValue);
        wrapper.appendChild(btn);
        return wrapper;
    }

    if (p.options && Array.isArray(p.options)) {
        const select = document.createElement('select');
        select.className = 'inline-select';
        select.dataset.paramId = p.id;
        p.options.forEach(optionValue => {
            const option = document.createElement('option');
            option.value = String(optionValue);
            option.textContent = String(optionValue);
            option.selected = String(optionValue) === String(currentValue);
            select.appendChild(option);
        });
        wrapper.appendChild(select);
        return wrapper;
    }

    const input = document.createElement('input');
    input.className = 'inline-input';
    input.dataset.paramId = p.id;
    input.id = `inline-param-${++inlineInputSeq}`;
    input.value = inlineInputValue(currentValue, p);
    syncInlineInputWidth(input);
    if (p.type === 'int' || p.type === 'float') {
        input.type = 'text';
        input.inputMode = p.type === 'float' ? 'decimal' : 'numeric';
        if (Array.isArray(p.range)) {
            input.dataset.min = String(p.range[0]);
            input.dataset.max = String(p.range[1]);
        }
    } else {
        input.type = 'text';
    }
    wrapper.appendChild(input);
    return wrapper;
}

function bindInlineControls(container) {
    container.querySelectorAll('.inline-input').forEach(input => {
        input.addEventListener('input', () => {
            const p = findParam(input.dataset.paramId);
            if (!p) return;
            syncInlineInputWidth(input);
            setParamValue(p, input.value);
        });
    });

    container.querySelectorAll('.inline-select').forEach(select => {
        select.addEventListener('change', () => {
            const p = findParam(select.dataset.paramId);
            if (p) setParamValue(p, select.value);
        });
    });

    container.querySelectorAll('.inline-toggle').forEach(btn => {
        btn.addEventListener('click', () => {
            const p = findParam(btn.dataset.paramId);
            if (!p) return;
            const current = modifiedValues[p.id] !== undefined ? modifiedValues[p.id] : p.value;
            const next = !(current === true || current === 'True' || current === 1);
            btn.textContent = next ? 'True' : 'False';
            setParamValue(p, next ? 'True' : 'False');
        });
    });
}

function inlineInputValue(value, p) {
    if (p.type === 'list' && Array.isArray(value)) return value.join(', ');
    return String(value ?? '');
}

function syncInlineInputWidth(input) {
    const length = Math.max(1, input.value.length);
    input.style.width = `${Math.min(18, Math.max(2, length)) + 1.2}ch`;
}

function findParam(id) {
    return params.find(p => p.id === id);
}

function inlineParamTitle(p) {
    const label = p.description || p.presetDesc || p.name;
    const range = Array.isArray(p.range) ? `；范围 ${p.range[0]} ~ ${p.range[1]}` : '';
    return `${p.name}: ${label}${range}`;
}

function syncInlineModifiedState() {
    document.querySelectorAll('.inline-param').forEach(el => {
        el.classList.toggle('modified', modifiedValues[el.dataset.paramId] !== undefined);
    });
}

function setParamValue(p, newValue) {
    if (p.type === 'int') {
        newValue = parseInt(newValue);
        if (isNaN(newValue)) return;
    } else if (p.type === 'float') {
        newValue = parseFloat(newValue);
        if (isNaN(newValue)) return;
    } else if (p.type === 'list') {
        newValue = newValue.split(',').map(s => s.trim()).filter(Boolean);
    }

    if (JSON.stringify(newValue) === JSON.stringify(p.value)) {
        delete modifiedValues[p.id];
    } else {
        modifiedValues[p.id] = newValue;
    }

    // M8: Defer DOM class toggle to scheduleUpdate
    scheduleUpdate();
}

function scheduleUpdate() {
    if (updateTimer) cancelAnimationFrame(updateTimer);
    updateTimer = requestAnimationFrame(() => {
        updateOutputCode();
        syncInlineModifiedState();
    });
}

// ── Output Code Generation ──
function updateOutputCode() {
    const lines = sourceCode.split('\n');
    const changes = [];

    // H2/H3: Use character-offset approach for reliable multi-line + same-line replacement.
    // Build a flat char array from lines, apply replacements by absolute offset, then split back.
    const fullText = sourceCode;
    const lineOffsets = []; // cumulative char offset for each line start
    let offset = 0;
    for (const line of lines) {
        lineOffsets.push(offset);
        offset += line.length + 1; // +1 for \n
    }

    // Convert (line, col) to absolute char offset with bounds checking
    function toAbsOffset(line, col) {
        if (line < 1 || line > lineOffsets.length) return -1;
        return lineOffsets[line - 1] + col;
    }

    // Sort by absolute offset descending so replacements don't shift later ones
    const sorted = [...params]
        .filter(p => modifiedValues[p.id] !== undefined)
        .map(p => ({
            ...p,
            absStart: toAbsOffset(p.line, p.col),
            absEnd: toAbsOffset(p.endLine, p.endCol),
        }))
        .filter(p => p.absStart >= 0 && p.absEnd >= 0 && p.absStart <= p.absEnd)
        .sort((a, b) => b.absStart - a.absStart);

    let result = fullText;
    sorted.forEach(p => {
        const newRaw = modifiedValues[p.id];
        let newText;
        if (p.type === 'string' || p.type === 'path') {
            // Escape backslashes, quotes, and special chars for safe Python string literal
            const orig = p.originalText || '';
            const quote = orig.startsWith('"') ? '"' : "'";
            const escaped = String(newRaw).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '\\"').replace(/\n/g, '\\n').replace(/\r/g, '\\r').replace(/\t/g, '\\t');
            newText = quote + escaped + quote;
        } else if (p.type === 'list') {
            // Generate proper Python literal with type-aware elements
            if (Array.isArray(newRaw)) {
                const elements = newRaw.map(el => {
                    if (typeof el === 'string') {
                        const esc = el.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '\\"');
                        return `'${esc}'`;
                    }
                    return String(el);
                });
                newText = `[${elements.join(', ')}]`;
            } else {
                newText = String(newRaw);
            }
        } else {
            newText = String(newRaw);
        }

        result = result.substring(0, p.absStart) + newText + result.substring(p.absEnd);
        changes.push({ name: p.name, oldVal: formatValue(p.value), newVal: formatValue(newRaw) });
    });

    // Avoid triggering unnecessary events
    if (outputEditor.getValue() !== result) {
        outputEditor.setValue(result);
    }

    // Highlight modified lines
    decorations = outputEditor.deltaDecorations(decorations,
        sorted.map(p => ({
            range: new monaco.Range(p.line, 1, p.line, 1),
            options: {
                isWholeLine: true,
                className: 'modified-line',
                glyphMarginClassName: 'modified-glyph',
            },
        }))
    );

    // Change summary
    const summary = document.getElementById('changeSummary');
    const changeList = document.getElementById('changeList');
    if (changes.length > 0) {
        summary.style.display = 'block';
        changeList.innerHTML = changes.map(c =>
            `<div class="change-item">${escHtml(c.name)}: <span class="change-old">${escHtml(c.oldVal)}</span><span class="change-arrow">→</span><span class="change-new">${escHtml(c.newVal)}</span></div>`
        ).join('');
    } else {
        summary.style.display = 'none';
    }
}

// ── Reset All ──
document.getElementById('btnResetAll').addEventListener('click', () => {
    modifiedValues = {};
    renderCodeReview();
    scheduleUpdate();
});

// ── Copy ──
document.getElementById('btnCopy').addEventListener('click', () => {
    navigator.clipboard.writeText(outputEditor.getValue()).then(() => {
        const btn = document.getElementById('btnCopy');
        btn.textContent = '已复制';
        setTimeout(() => btn.textContent = '复制', 1500);
    }).catch(() => {
        alert('复制失败，请手动选择代码复制 (Ctrl/Cmd+A, Ctrl/Cmd+C)');
    });
});

// ── Export ──
document.getElementById('btnExport').addEventListener('click', () => {
    const blob = new Blob([outputEditor.getValue()], { type: 'text/x-python' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'modified_script.py';
    a.click();
    URL.revokeObjectURL(url);
});

// ── Settings Modal ──
let _previouslyFocused = null;

async function openSettings() {
    let s = cachedSettings;
    try {
        s = await loadSettings();
    } catch (err) {
        alert(err.message);
        return;
    }

    const apiInput = document.getElementById('inputApiKey');
    apiInput.value = '';
    apiInput.placeholder = s.hasApiKey ? '已保存，留空保持不变' : 'sk-ant-... 或 sk-...';
    document.getElementById('apiKeyStatus').textContent = s.hasApiKey
        ? '已保存 API Key。新输入会覆盖旧 Key，留空则保持不变。'
        : 'API Key 只保存在本机后端配置中，不写入浏览器 localStorage。';
    document.getElementById('inputBaseUrl').value = s.baseUrl;
    document.getElementById('inputApiFormat').value = s.apiFormat;
    document.getElementById('inputModel').value = s.model;
    const modal = document.getElementById('settingsModal');
    _previouslyFocused = document.activeElement;
    modal.style.display = 'flex';
    apiInput.focus();
}

function closeSettings() {
    document.getElementById('settingsModal').style.display = 'none';
    if (_previouslyFocused) _previouslyFocused.focus();
}

document.getElementById('btnSettings').addEventListener('click', () => {
    openSettings();
});
document.getElementById('settingsClose').addEventListener('click', closeSettings);
document.getElementById('btnToggleKey').addEventListener('click', () => {
    const input = document.getElementById('inputApiKey');
    const btn = document.getElementById('btnToggleKey');
    if (input.type === 'password') {
        input.type = 'text';
        btn.textContent = '🙈';
    } else {
        input.type = 'password';
        btn.textContent = '👁';
    }
});
document.getElementById('settingsModal').addEventListener('click', (e) => {
    if (e.target.id === 'settingsModal') closeSettings();
});
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && document.getElementById('settingsModal').style.display === 'flex') {
        closeSettings();
    }
});
document.getElementById('btnSaveSettings').addEventListener('click', async () => {
    const btn = document.getElementById('btnSaveSettings');
    btn.disabled = true;
    btn.textContent = '保存中...';
    try {
        await saveSettings({
            apiKey: document.getElementById('inputApiKey').value.trim(),
            baseUrl: document.getElementById('inputBaseUrl').value.trim(),
            apiFormat: document.getElementById('inputApiFormat').value,
            model: document.getElementById('inputModel').value.trim(),
        });
        closeSettings();
    } catch (err) {
        alert(err.message);
    } finally {
        btn.disabled = false;
        btn.textContent = '保存';
    }
});

document.getElementById('btnClearApiKey').addEventListener('click', async () => {
    const btn = document.getElementById('btnClearApiKey');
    btn.disabled = true;
    btn.textContent = '清除中...';
    try {
        const s = await saveSettings({
            clearApiKey: true,
            baseUrl: document.getElementById('inputBaseUrl').value.trim(),
            apiFormat: document.getElementById('inputApiFormat').value,
            model: document.getElementById('inputModel').value.trim(),
        });
        document.getElementById('inputApiKey').value = '';
        document.getElementById('inputApiKey').placeholder = 'sk-ant-... 或 sk-...';
        document.getElementById('apiKeyStatus').textContent = s.hasApiKey
            ? '已保存 API Key。'
            : 'API Key 已清除。';
    } catch (err) {
        alert(err.message);
    } finally {
        btn.disabled = false;
        btn.textContent = '清除 Key';
    }
});

// ── Banner ──
document.getElementById('bannerClose').addEventListener('click', () => {
    document.getElementById('fallbackBanner').style.display = 'none';
});

// ── Resize Handles ──
document.querySelectorAll('.resize-handle').forEach(handle => {
    let startX, startY, leftPanel, rightPanel, startLeftW, startRightW, startLeftH, startRightH;

    handle.addEventListener('mousedown', (e) => {
        e.preventDefault();
        startX = e.clientX;
        startY = e.clientY;
        leftPanel = document.getElementById(handle.dataset.left);
        rightPanel = document.getElementById(handle.dataset.right);
        startLeftW = leftPanel.getBoundingClientRect().width;
        startRightW = rightPanel.getBoundingClientRect().width;
        startLeftH = leftPanel.getBoundingClientRect().height;
        startRightH = rightPanel.getBoundingClientRect().height;
        handle.classList.add('active');
        // Detect if layout is vertical (mobile) based on panel stacking
        const isVertical = window.getComputedStyle(leftPanel.parentElement).flexDirection === 'column';
        document.body.style.cursor = isVertical ? 'row-resize' : 'col-resize';
        document.body.style.userSelect = 'none';

        const onMove = (e) => {
            if (isVertical) {
                const dy = e.clientY - startY;
                const newLeft = Math.max(150, startLeftH + dy);
                const newRight = Math.max(150, startRightH - dy);
                leftPanel.style.flex = `0 0 ${newLeft}px`;
                rightPanel.style.flex = `0 0 ${newRight}px`;
            } else {
                const dx = e.clientX - startX;
                const newLeft = Math.max(200, startLeftW + dx);
                const newRight = Math.max(200, startRightW - dx);
                leftPanel.style.flex = `0 0 ${newLeft}px`;
                rightPanel.style.flex = `0 0 ${newRight}px`;
            }
        };
        const onUp = () => {
            handle.classList.remove('active');
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
            sourceEditor.layout();
            outputEditor.layout();
        };
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
    });
});

// ── Helpers ──
function guessEditType(p) {
    if (p.type === 'bool') return 'toggle';
    if (p.type === 'path') return 'path';
    if (p.options) return 'select';
    if ((p.type === 'int' || p.type === 'float') && p.range) return 'slider';
    return 'number';
}

function notebookToPython(rawText) {
    let notebook;
    try {
        notebook = JSON.parse(rawText);
    } catch (err) {
        throw new Error('不是有效的 ipynb JSON 文件');
    }
    if (!Array.isArray(notebook.cells)) {
        throw new Error('缺少 cells 字段');
    }

    const chunks = [];
    notebook.cells.forEach((cell, index) => {
        if (cell.cell_type !== 'code') return;
        const source = Array.isArray(cell.source) ? cell.source.join('') : String(cell.source || '');
        if (!source.trim()) return;
        if (chunks.length) chunks.push('');
        chunks.push(`# %% Notebook cell ${index + 1}`);
        chunks.push(source.replace(/\s+$/g, ''));
    });
    if (!chunks.length) {
        throw new Error('没有可分析的 code cell');
    }
    return chunks.join('\n') + '\n';
}

function normalizeClientSections(rawSections, code) {
    const lineCount = Math.max(1, code.split('\n').length);
    const clean = Array.isArray(rawSections)
        ? rawSections.map(section => ({
            title: String(section?.title || '代码片段').slice(0, 24),
            start_line: Number(section?.start_line),
            end_line: Number(section?.end_line),
            explanation: String(section?.explanation || '').slice(0, 500),
        })).filter(section =>
            Number.isInteger(section.start_line) &&
            Number.isInteger(section.end_line) &&
            section.start_line >= 1 &&
            section.end_line >= section.start_line
        )
        : [];

    if (!clean.length) {
        return [{
            title: '脚本代码',
            start_line: 1,
            end_line: lineCount,
            explanation: '这里展示完整脚本代码。当前没有可用的 AI 分段解释，因此先作为一个整体呈现；高亮输入块仍然是可调参数位置。',
        }];
    }

    return clean
        .sort((a, b) => a.start_line - b.start_line || a.end_line - b.end_line)
        .map(section => ({
            ...section,
            start_line: Math.min(Math.max(1, section.start_line), lineCount),
            end_line: Math.min(Math.max(1, section.end_line), lineCount),
        }))
        .filter(section => section.end_line >= section.start_line);
}

function formatValue(v) {
    if (typeof v === 'boolean') return v ? 'True' : 'False';
    if (Array.isArray(v)) return `[${v.join(', ')}]`;
    if (v === null || v === undefined) return 'None';
    return String(v);
}

// L10: Regex-based escaper (no DOM allocation)
function escHtml(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// C1: Attribute-value escaper (includes quote escaping)
function escAttr(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
