class MyAgentApp {
    constructor() {
        this.apiBase = "/api";
        this.sessionId = this.createSessionId();
        this.currentMode = "stream";
        this.currentUserId = "default";
        this.isBusy = false;
        this.themeStorageKey = "myagent-theme";
        this.bindElements();
        this.applyStoredTheme();
        if (this.modeSelect) {
            this.modeSelect.value = "stream";
        }
        this.bindEvents();
        this.bootstrap();
    }

    bindElements() {
        this.sessionList = document.getElementById("sessionList");
        this.documentList = document.getElementById("documentList");
        this.chatMessages = document.getElementById("chatMessages");
        this.statsPanel = document.getElementById("statsPanel");
        this.diagnosisOutput = document.getElementById("diagnosisOutput");
        this.statusText = document.getElementById("statusText");
        this.newSessionBtn = document.getElementById("newSessionBtn");
        this.refreshStatsBtn = document.getElementById("refreshStatsBtn");
        this.diagnoseBtn = document.getElementById("diagnoseBtn");
        this.fileInput = document.getElementById("fileInput");
        this.modeSelect = document.getElementById("modeSelect");
        this.messageInput = document.getElementById("messageInput");
        this.sendBtn = document.getElementById("sendBtn");
        this.messageTemplate = document.getElementById("messageTemplate");
        this.themeToggleBtn = document.getElementById("themeToggleBtn");
    }

    bindEvents() {
        this.newSessionBtn.addEventListener("click", () => this.resetSession());
        this.refreshStatsBtn.addEventListener("click", () => this.refreshWorkspace());
        this.diagnoseBtn.addEventListener("click", () => this.runWorkspaceInsight());
        this.fileInput.addEventListener("change", (event) => this.uploadFiles(event.target.files));
        this.modeSelect.addEventListener("change", (event) => {
            this.currentMode = event.target.value;
        });
        this.sendBtn.addEventListener("click", () => this.handleSend());
        this.messageInput.addEventListener("keydown", (event) => {
            if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                this.handleSend();
            }
        });
        if (this.themeToggleBtn) {
            this.themeToggleBtn.addEventListener("click", () => this.toggleTheme());
        }
    }

    async bootstrap() {
        await this.refreshWorkspace();
        this.renderEmptyMessage();
    }

    async refreshWorkspace() {
        await Promise.all([
            this.loadHealth(),
            this.loadSessions(),
            this.loadDocuments(),
        ]);
    }

    async loadHealth() {
        const data = await this.request("/health");
        const payload = data.data || {};
        this.statusText.textContent = `工作区：${payload.workspace || "-"} | 文件数：${payload.indexed_files || 0} | 分块数：${payload.indexed_chunks || 0}`;
        this.renderStats(payload);
    }

    async loadSessions() {
        const data = await this.request(`/chat/sessions?user_id=${encodeURIComponent(this.currentUserId)}`);
        this.renderSessions(data.data || []);
    }

    async loadDocuments() {
        const data = await this.request("/documents");
        this.renderDocuments(data.data || []);
    }

    renderStats(payload) {
        const entries = [
            ["已索引文档", payload.indexed_files || 0],
            ["已索引分块", payload.indexed_chunks || 0],
            ["文档总数", (payload.documents || []).length],
            ["服务状态", payload.status || "未知"],
        ];
        this.statsPanel.innerHTML = "";
        for (const [label, value] of entries) {
            const card = document.createElement("div");
            card.className = "stat-card";
            card.innerHTML = `<div class="stat-label">${label}</div><div class="stat-value">${value}</div>`;
            this.statsPanel.appendChild(card);
        }
    }

    renderSessions(sessions) {
        this.sessionList.innerHTML = "";
        if (!sessions.length) {
            this.sessionList.innerHTML = `<div class="empty-state">暂无历史会话</div>`;
            return;
        }

        sessions.forEach((session) => {
            const item = document.createElement("div");
            item.className = "session-item";

            const main = document.createElement("div");
            main.className = "session-main";
            const title = session.title || session.session_id;
            main.innerHTML = `
                <div class="session-title">${this.escapeHtml(title)}</div>
                <div class="session-meta">${new Date((session.updated_at || 0) * 1000).toLocaleString()}</div>
            `;
            main.addEventListener("click", () => this.openSession(session.session_id));

            const clearBtn = document.createElement("button");
            clearBtn.textContent = "清空";
            clearBtn.addEventListener("click", async (event) => {
                event.stopPropagation();
                await this.clearSession(session.session_id);
            });

            item.appendChild(main);
            item.appendChild(clearBtn);
            this.sessionList.appendChild(item);
        });
    }

    renderDocuments(documents) {
        this.documentList.innerHTML = "";
        if (!documents.length) {
            this.documentList.innerHTML = `<div class="empty-state">当前还没有入库文档</div>`;
            return;
        }

        documents.forEach((doc) => {
            const item = document.createElement("div");
            item.className = "document-item";
            item.innerHTML = `
                <div class="document-name">${this.escapeHtml(doc)}</div>
                <div class="document-meta">${this.escapeHtml(this.basename(doc))}</div>
            `;
            this.documentList.appendChild(item);
        });
    }

    renderEmptyMessage() {
        if (this.chatMessages.children.length > 0) {
            return;
        }
        this.chatMessages.innerHTML = `<div class="empty-state">请先上传文档，然后开始提问</div>`;
    }

    resetSession() {
        this.sessionId = this.createSessionId();
        this.chatMessages.innerHTML = "";
        this.renderEmptyMessage();
    }

    async openSession(sessionId) {
        const data = await this.request(`/chat/session/${encodeURIComponent(sessionId)}`);
        const payload = data.data || {};
        this.sessionId = sessionId;
        this.chatMessages.innerHTML = "";
        const history = payload.history || [];
        if (!history.length) {
            this.renderEmptyMessage();
            return;
        }
        history.forEach((message) => {
            this.appendMessage(message.role, message.content, message.role === "assistant");
        });
    }

    async clearSession(sessionId) {
        await this.request("/chat/clear", {
            method: "POST",
            body: JSON.stringify({ session_id: sessionId }),
        });
        if (this.sessionId === sessionId) {
            this.resetSession();
        }
        await this.loadSessions();
    }

    async handleSend() {
        const question = this.messageInput.value.trim();
        if (!question || this.isBusy) {
            return;
        }

        this.isBusy = true;
        this.sendBtn.disabled = true;
        this.appendMessage("user", question);
        this.messageInput.value = "";

        try {
            if (this.currentMode === "quick") {
                await this.sendQuick(question);
            } else {
                await this.sendStream(question);
            }
            await this.loadSessions();
        } catch (error) {
            this.appendMessage("assistant", `请求失败：${error.message}`);
        } finally {
            this.isBusy = false;
            this.sendBtn.disabled = false;
        }
    }

    async sendQuick(question) {
        const data = await this.request("/chat", {
            method: "POST",
            body: JSON.stringify({
                question,
                session_id: this.sessionId,
                user_id: this.currentUserId,
                top_k: 4,
            }),
        });
        const answer = data.data?.answer || "没有返回回答内容";
        this.appendMessage("assistant", answer, true);
    }

    async sendStream(question) {
        const response = await fetch(`${this.apiBase}/chat_stream`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                question,
                session_id: this.sessionId,
                user_id: this.currentUserId,
                top_k: 4,
            }),
        });
        if (!response.ok) {
            throw new Error(`接口状态异常：HTTP ${response.status}`);
        }

        const assistantNode = this.appendMessage("assistant", "", true, true);
        const body = assistantNode.querySelector(".message-body");
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let fullResponse = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) {
                break;
            }
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() || "";
            for (const line of lines) {
                if (!line.startsWith("data:")) {
                    continue;
                }
                const raw = line.slice(5).trim();
                if (!raw) {
                    continue;
                }
                const payload = JSON.parse(raw);
                if (payload.type === "content") {
                    fullResponse += payload.data || "";
                    this.renderMessageContent(body, fullResponse, false);
                } else if (payload.type === "done") {
                    fullResponse = payload.data?.answer || fullResponse;
                    this.renderMessageContent(body, fullResponse, true);
                } else if (payload.type === "error") {
                    throw new Error(payload.data || "流式响应失败");
                }
                this.scrollToBottom();
            }
        }
    }

    async uploadFiles(fileList) {
        const files = Array.from(fileList || []);
        if (!files.length) {
            return;
        }

        for (const file of files) {
            const formData = new FormData();
            formData.append("file", file);
            formData.append("user_id", this.currentUserId);
            formData.append("private", "false");
            try {
                const response = await fetch(`${this.apiBase}/upload`, {
                    method: "POST",
                    body: formData,
                });
                const payload = await response.json();
                if (!response.ok || payload.code !== 200) {
                    throw new Error(payload.detail || payload.message || "上传失败");
                }
                this.appendMessage("assistant", `文件已入库：${payload.data.filename}（共 ${payload.data.chunks} 个分块）`);
            } catch (error) {
                this.appendMessage("assistant", `文件 ${file.name} 上传失败：${error.message}`);
            }
        }

        this.fileInput.value = "";
        await this.refreshWorkspace();
    }

    async runWorkspaceInsight() {
        this.diagnosisOutput.textContent = "正在分析工作区...\n";
        const response = await fetch(`${this.apiBase}/aiops`, { method: "POST" });
        if (!response.ok) {
            this.diagnosisOutput.textContent = `分析失败：HTTP ${response.status}`;
            return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let output = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) {
                break;
            }
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() || "";
            for (const line of lines) {
                if (!line.startsWith("data:")) {
                    continue;
                }
                const raw = line.slice(5).trim();
                if (!raw) {
                    continue;
                }
                const payload = JSON.parse(raw);
                if (payload.type === "status") {
                    output += `${payload.data}\n`;
                } else if (payload.type === "report") {
                    output += `\n文档列表：\n${payload.data}\n`;
                } else if (payload.type === "done") {
                    output += `\n汇总结果：\n${JSON.stringify(payload.data, null, 2)}`;
                }
                this.diagnosisOutput.textContent = output;
            }
        }
    }

    appendMessage(role, content, markdown = false, replaceEmpty = false) {
        if (this.chatMessages.querySelector(".empty-state")) {
            this.chatMessages.innerHTML = "";
        }

        let node = null;
        if (replaceEmpty) {
            node = this.messageTemplate.content.firstElementChild.cloneNode(true);
            node.classList.add(role);
            node.querySelector(".message-role").textContent = this.getRoleLabel(role);
            this.chatMessages.appendChild(node);
        } else {
            node = this.messageTemplate.content.firstElementChild.cloneNode(true);
            node.classList.add(role);
            node.querySelector(".message-role").textContent = this.getRoleLabel(role);
            const body = node.querySelector(".message-body");
            if (markdown) {
                this.renderMessageContent(body, content, true);
            } else {
                body.textContent = content;
            }
            this.chatMessages.appendChild(node);
        }
        this.scrollToBottom();
        return node;
    }

    renderMarkdown(content) {
        if (!content) {
            return "";
        }
        if (window.marked) {
            const preserved = this.preserveMath(content);
            return this.restoreMath(marked.parse(preserved.text), preserved.tokens);
        }
        return this.escapeHtml(content);
    }

    renderMessageContent(container, content, forceMathRender = false) {
        if (!container) {
            return;
        }

        container.innerHTML = this.renderMarkdown(content);
        if (forceMathRender || this.hasBalancedMath(content)) {
            this.renderMath(container);
        }
        this.highlightCode(container);
    }

    preserveMath(content) {
        const tokens = [];
        const patterns = [
            /\$\$[\s\S]+?\$\$/g,
            /\\\[[\s\S]+?\\\]/g,
            /\\\([\s\S]+?\\\)/g,
            /(?<!\$)\$[^$\n]+\$(?!\$)/g,
        ];

        let text = content;
        patterns.forEach((pattern) => {
            text = text.replace(pattern, (match) => {
                const key = `MATH_TOKEN_${tokens.length}`;
                tokens.push({
                    key,
                    value: this.escapeHtml(match),
                });
                return key;
            });
        });

        return { text, tokens };
    }

    restoreMath(html, tokens) {
        return tokens.reduce((result, token) => {
            return result.replaceAll(token.key, token.value);
        }, html);
    }

    hasBalancedMath(content) {
        return (
            this.hasBalancedInlineDollar(content)
            && this.hasBalancedDoubleDollar(content)
            && this.hasBalancedEscapedPair(content, "\\(", "\\)")
            && this.hasBalancedEscapedPair(content, "\\[", "\\]")
        );
    }

    hasBalancedInlineDollar(content) {
        const normalized = content.replace(/\$\$/g, "");
        const matches = normalized.match(/(?<!\\)\$/g) || [];
        return matches.length % 2 === 0;
    }

    hasBalancedDoubleDollar(content) {
        return (content.match(/\$\$/g) || []).length % 2 === 0;
    }

    hasBalancedEscapedPair(content, left, right) {
        const leftCount = content.split(left).length - 1;
        const rightCount = content.split(right).length - 1;
        return leftCount === rightCount;
    }

    highlightCode(container) {
        if (!window.hljs || !container) {
            return;
        }
        container.querySelectorAll("pre code").forEach((block) => {
            hljs.highlightElement(block);
        });
    }

    renderMath(container) {
        if (!container || typeof window.renderMathInElement !== "function") {
            return;
        }

        window.renderMathInElement(container, {
            throwOnError: false,
            delimiters: [
                { left: "$$", right: "$$", display: true },
                { left: "\\[", right: "\\]", display: true },
                { left: "$", right: "$", display: false },
                { left: "\\(", right: "\\)", display: false },
            ],
            ignoredTags: ["script", "noscript", "style", "textarea", "pre", "code"],
        });
    }

    scrollToBottom() {
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }

    async request(path, options = {}) {
        const response = await fetch(`${this.apiBase}${path}`, {
            headers: {
                "Content-Type": "application/json",
                ...(options.headers || {}),
            },
            ...options,
        });
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.detail || payload.message || `HTTP ${response.status}`);
        }
        return payload;
    }

    createSessionId() {
        return `session_${Math.random().toString(36).slice(2, 10)}_${Date.now()}`;
    }

    applyStoredTheme() {
        const stored = localStorage.getItem(this.themeStorageKey);
        const theme = stored === "light" ? "light" : "dark";
        document.body.dataset.theme = theme;
        this.updateThemeAssets(theme);
    }

    toggleTheme() {
        const current = document.body.dataset.theme === "light" ? "light" : "dark";
        const next = current === "light" ? "dark" : "light";
        document.body.dataset.theme = next;
        localStorage.setItem(this.themeStorageKey, next);
        this.updateThemeAssets(next);
    }

    updateThemeAssets(theme) {
        this.updateThemeToggleLabel(theme);

        const darkTheme = document.getElementById("hljs-dark-theme");
        const lightTheme = document.getElementById("hljs-light-theme");
        if (darkTheme && lightTheme) {
            const isLight = theme === "light";
            darkTheme.disabled = isLight;
            lightTheme.disabled = !isLight;
        }
    }

    updateThemeToggleLabel(theme) {
        if (!this.themeToggleBtn) {
            return;
        }
        this.themeToggleBtn.textContent = theme === "light" ? "深色模式" : "浅色模式";
    }

    basename(path) {
        const parts = String(path).split(/[\\/]/);
        return parts[parts.length - 1] || path;
    }

    getRoleLabel(role) {
        if (role === "user") {
            return "用户";
        }
        if (role === "assistant") {
            return "助手";
        }
        return role;
    }

    escapeHtml(value) {
        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }
}


window.addEventListener("DOMContentLoaded", () => {
    new MyAgentApp();
});

