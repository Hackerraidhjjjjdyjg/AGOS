// AGOS — Operating System UI Logic
// Window management, drag, resize, taskbar, app launcher, terminal

const API = window.location.origin;
let taskCount = 0;
let tokenCount = 0;

// DOM Cache to avoid repeated querying
const dockItemsMap = new Map();
document.querySelectorAll('.dock-item').forEach(d => {
    if (d.dataset.app) dockItemsMap.set(d.dataset.app, d);
});

let currentlyFocusedWindow = document.querySelector('.window.focused');

// ─── Window Management ──────────────────────────

let topZ = 100;

function openApp(appName) {
    const win = document.getElementById(`win-${appName}`);
    if (!win) return;
    win.classList.remove('hidden', 'minimized');
    focusWindow(win);
    // Mark dock active
    const dockItem = dockItemsMap.get(appName);
    if (dockItem) dockItem.classList.add('active');
}

function closeApp(win) {
    win.classList.add('hidden');
    const appName = win.id.replace('win-', '');
    const dockItem = dockItemsMap.get(appName);
    if (dockItem) dockItem.classList.remove('active');
}

function minimizeApp(win) {
    win.classList.add('minimized');
}

function maximizeApp(win) {
    if (win.dataset.maximized === 'true') {
        win.style.top = win.dataset.origTop;
        win.style.left = win.dataset.origLeft;
        win.style.width = win.dataset.origWidth;
        win.style.height = win.dataset.origHeight;
        win.dataset.maximized = 'false';
    } else {
        win.dataset.origTop = win.style.top;
        win.dataset.origLeft = win.style.left;
        win.dataset.origWidth = win.style.width;
        win.dataset.origHeight = win.style.height;
        win.style.top = '0';
        win.style.left = '0';
        win.style.width = '100%';
        win.style.height = 'calc(100vh - 48px)';
        win.dataset.maximized = 'true';
    }
    focusWindow(win);
}

function focusWindow(win) {
    if (currentlyFocusedWindow) {
        currentlyFocusedWindow.classList.remove('focused');
    }
    win.classList.add('focused');
    currentlyFocusedWindow = win;
    topZ++;
    win.style.zIndex = topZ;
}

// Window button clicks
document.querySelectorAll('.win-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const win = btn.closest('.window');
        const action = btn.dataset.action;
        if (action === 'close') closeApp(win);
        else if (action === 'minimize') minimizeApp(win);
        else if (action === 'maximize') maximizeApp(win);
    });
});

// Click window to focus
document.querySelectorAll('.window').forEach(win => {
    win.addEventListener('mousedown', () => focusWindow(win));
});

// ─── Drag Windows ───────────────────────────────

document.querySelectorAll('.window-titlebar').forEach(titlebar => {
    let isDrag = false, startX, startY, origX, origY;

    titlebar.addEventListener('mousedown', (e) => {
        if (e.target.classList.contains('win-btn')) return;
        const win = document.getElementById(titlebar.dataset.win);
        if (win.dataset.maximized === 'true') return;
        isDrag = true;
        startX = e.clientX;
        startY = e.clientY;
        origX = win.offsetLeft;
        origY = win.offsetTop;
        focusWindow(win);
        e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
        if (!isDrag) return;
        const win = document.getElementById(titlebar.dataset.win);
        win.style.left = (origX + e.clientX - startX) + 'px';
        win.style.top = (origY + e.clientY - startY) + 'px';
    });

    document.addEventListener('mouseup', () => { isDrag = false; });
});

// Double-click titlebar to maximize
document.querySelectorAll('.window-titlebar').forEach(tb => {
    tb.addEventListener('dblclick', () => {
        const win = document.getElementById(tb.dataset.win);
        maximizeApp(win);
    });
});

// ─── Resize Windows ─────────────────────────────

document.querySelectorAll('.window').forEach(win => {
    let isResize = false, startX, startY, startW, startH;

    win.addEventListener('mousedown', (e) => {
        const rect = win.getBoundingClientRect();
        if (e.clientX > rect.right - 16 && e.clientY > rect.bottom - 16) {
            isResize = true;
            startX = e.clientX;
            startY = e.clientY;
            startW = rect.width;
            startH = rect.height;
            e.preventDefault();
        }
    });

    document.addEventListener('mousemove', (e) => {
        if (!isResize) return;
        win.style.width = Math.max(320, startW + e.clientX - startX) + 'px';
        win.style.height = Math.max(200, startH + e.clientY - startY) + 'px';
    });

    document.addEventListener('mouseup', () => { isResize = false; });
});

// ─── Desktop Icons ──────────────────────────────

document.querySelectorAll('.desktop-icon').forEach(icon => {
    icon.addEventListener('dblclick', () => openApp(icon.dataset.app));
});

// ─── Dock Items ─────────────────────────────────

document.querySelectorAll('.dock-item').forEach(item => {
    item.addEventListener('click', () => {
        const app = item.dataset.app;
        const win = document.getElementById(`win-${app}`);
        if (win.classList.contains('hidden') || win.classList.contains('minimized')) {
            openApp(app);
        } else if (win.classList.contains('focused')) {
            minimizeApp(win);
        } else {
            focusWindow(win);
        }
    });
});

// ─── App Launcher ───────────────────────────────

const launcherOverlay = document.getElementById('launcherOverlay');
const launcherBtn = document.getElementById('launcherBtn');
const launcherSearch = document.getElementById('launcherSearch');

launcherBtn.addEventListener('click', () => {
    launcherOverlay.classList.toggle('hidden');
    if (!launcherOverlay.classList.contains('hidden')) {
        launcherSearch.value = '';
        launcherSearch.focus();
    }
});

launcherOverlay.addEventListener('click', (e) => {
    if (e.target === launcherOverlay) launcherOverlay.classList.add('hidden');
});

document.querySelectorAll('.launcher-app').forEach(app => {
    app.addEventListener('click', () => {
        openApp(app.dataset.app);
        launcherOverlay.classList.add('hidden');
    });
});

// Escape closes launcher
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') launcherOverlay.classList.add('hidden');
    if ((e.metaKey || e.ctrlKey) && e.key === ' ') {
        e.preventDefault();
        launcherOverlay.classList.toggle('hidden');
    }
});

// ─── Terminal ───────────────────────────────────

const termForm = document.getElementById('termForm');
const termInput = document.getElementById('termInput');
const termOutput = document.getElementById('termOutput');

// Click hints to run
termOutput.addEventListener('click', (e) => {
    if (e.target.classList.contains('cmd-hint')) {
        termInput.value = e.target.textContent;
        termInput.focus();
    }
});

termForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const cmd = termInput.value.trim();
    if (!cmd) return;

    addTermLine('user', cmd);
    termInput.value = '';
    termInput.disabled = true;

    const loadingLine = addTermLine('sys', '⏳ submitting to kernel...');

    try {
        const resp = await fetch(`${API}/api/v1/execute`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ intent: cmd, priority: 2 }),
        });
        const task = await resp.json();
        
        loadingLine.textContent = `⏳ task ${task.task_id} queued...`;
        
        // Polling loop
        let attempts = 0;
        const maxAttempts = 60; // 60 seconds timeout
        const poll = async () => {
            if (attempts >= maxAttempts) {
                loadingLine.remove();
                addTermLine('err', '❌ execution timed out after 60s');
                termInput.disabled = false;
                return;
            }

            const statusResp = await fetch(`${API}/api/v1/execute/${task.task_id}`);
            const data = await statusResp.json();

            if (data.status === 'completed' || data.status === 'failed') {
                loadingLine.remove();
                
                // Track tool calls to prevent double-printing
                let toolRendered = false;
                if (data.tool_calls && data.tool_calls.length > 0) {
                    data.tool_calls.forEach(tc => {
                        const icon = tc.error ? '❌' : '✅';
                        addTermLine('ok', `${icon} ${tc.tool}: ${tc.result || tc.error || 'OK'}`);
                        toolRendered = true;
                    });
                }
                
                // Only print output if it differs from the tool rendering or if no tools were called
                if (data.output && (!toolRendered || data.output.length > 100)) {
                    addTermLine('result', data.output);
                }
                
                if (data.error) {
                    addTermLine('err', `ERROR: ${data.error}`);
                }
                
                if (data.tokens_used) {
                    const costLine = data.cost_usd ? ` | cost: $${data.cost_usd.toFixed(4)}` : '';
                    addTermLine('sys', `📊 mission: ${data.agent_uuid.substring(0,8)}... | tokens: ${data.tokens_used}${costLine}`);
                    tokenCount += data.tokens_used;
                    document.getElementById('agentTokens').textContent = tokenCount;
                }

                taskCount++;
                document.getElementById('agentTasks').textContent = taskCount;
                termInput.disabled = false;
                termInput.focus();
                
                // Refresh audit log
                refreshAudit();
            } else {
                loadingLine.textContent = `⏳ task ${task.task_id} ${data.status}...`;
                attempts++;
                setTimeout(poll, 1000);
            }
        };

        setTimeout(poll, 500);

    } catch (err) {
        loadingLine.remove();
        addTermLine('err', `⚠ daemon offline: ${err.message}`);
        termInput.disabled = false;
    }
});

function addTermLine(cls, text) {
    const div = document.createElement('div');
    div.className = `term-line ${cls}`;
    div.textContent = text;
    termOutput.appendChild(div);
    termOutput.scrollTop = termOutput.scrollHeight;
    return div;
}

// ─── Audit Log ──────────────────────────────────

async function refreshAudit() {
    try {
        const resp = await fetch(`${API}/api/v1/audit`);
        const data = await resp.json();
        const tbody = document.getElementById('auditBody');
        tbody.innerHTML = '';
        
        data.reverse().forEach(entry => {
            const tr = document.createElement('tr');
            const decisionColor = entry.decision === 'ALLOWED' || entry.decision === 'SUCCESS' ? 'var(--green)' : 'var(--red)';
            tr.innerHTML = `
                <td style="font-family:var(--mono);font-size:11px">${entry.time}</td>
                <td><span style="font-family:var(--mono);font-size:10px;opacity:0.6">${(entry.agent_uuid || 'N/A').substring(0,6)}:</span> ${escapeHtml(entry.action)}</td>
                <td>${entry.resource}</td>
                <td style="color:${decisionColor}">${entry.decision}</td>
            `;
            if (entry.thought) {
                tr.title = `Thought: ${entry.thought}`;
            }
            tbody.appendChild(tr);
        });
    } catch (err) {
        console.error("Failed to fetch audit log:", err);
    }
}

function escapeHtml(str) {
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}

// ─── Clock ──────────────────────────────────────

function updateClock() {
    const now = new Date();
    document.getElementById('trayClock').textContent =
        now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}
setInterval(updateClock, 1000);
updateClock();

// ─── Health & Telemetry ──────────────────────────

async function updateTelemetry() {
    try {
        const resp = await fetch(`${API}/api/v1/telemetry`);
        const data = await resp.json();
        
        // Update UI status
        document.getElementById('trayStatus').style.color = 'var(--green)';
        
        // Update CPU Ring
        const cpu = Math.round(data.cpu);
        const cpuFill = document.querySelector('#cpuRing .ring-fill');
        if (cpuFill) cpuFill.setAttribute('stroke-dasharray', `${cpu} ${100 - cpu}`);
        const cpuVal = document.querySelector('#cpuRing .ring-val');
        if (cpuVal) cpuVal.textContent = `${cpu}%`;
        
        // Update Memory / Other stats if needed
        // (Assuming similar rings for memory if added to HTML)

        // Update global counters
        taskCount = data.tasks;
        document.getElementById('agentTasks').textContent = taskCount;

    } catch (err) {
        document.getElementById('trayStatus').style.color = 'var(--red)';
    }
}
setInterval(updateTelemetry, 3000);
updateTelemetry();
refreshAudit();

// Open terminal by default
openApp('terminal');
