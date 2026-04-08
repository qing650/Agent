class NovelStudioApp {
    constructor() {
        this.apiBase = "/api/novel";
        this.project = null;
        this.historyProjects = [];
        this.currentOutlineId = null;
        this.currentChapterId = null;
        this.themeStorageKey = "myagent-theme";
        this.lastProjectStorageKey = "myagent-novel-last-project";
        this.bindElements();
        this.applyStoredTheme();
        this.bindEvents();
        this.initialize();
    }

    bindElements() {
        this.novelIdInput = document.getElementById("novelIdInput");
        this.novelTitleInput = document.getElementById("novelTitleInput");
        this.novelTagsInput = document.getElementById("novelTagsInput");
        this.styleTagsInput = document.getElementById("styleTagsInput");
        this.loadProjectBtn = document.getElementById("loadProjectBtn");
        this.projectMeta = document.getElementById("projectMeta");
        this.novelStatusText = document.getElementById("novelStatusText");
        this.themeToggleBtn = document.getElementById("themeToggleBtn");
        this.historyProjectList = document.getElementById("historyProjectList");

        this.targetLengthInput = document.getElementById("targetLengthInput");
        this.outlineIdeaInput = document.getElementById("outlineIdeaInput");
        this.generateOutlineBtn = document.getElementById("generateOutlineBtn");
        this.saveOutlineBtn = document.getElementById("saveOutlineBtn");
        this.outlineContentOutput = document.getElementById("outlineContentOutput");

        this.chapterLengthInput = document.getElementById("chapterLengthInput");
        this.chapterCountInput = document.getElementById("chapterCountInput");
        this.chapterIdeaInput = document.getElementById("chapterIdeaInput");
        this.generateChapterBtn = document.getElementById("generateChapterBtn");
        this.refreshProjectBtn = document.getElementById("refreshProjectBtn");
        this.chapterList = document.getElementById("chapterList");

        this.chapterTitleInput = document.getElementById("chapterTitleInput");
        this.chapterSummaryInput = document.getElementById("chapterSummaryInput");
        this.chapterPredictionInput = document.getElementById("chapterPredictionInput");
        this.chapterContentOutput = document.getElementById("chapterContentOutput");
        this.saveChapterBtn = document.getElementById("saveChapterBtn");
    }

    bindEvents() {
        this.loadProjectBtn.addEventListener("click", () => this.loadProjectFromInput());
        this.refreshProjectBtn.addEventListener("click", () => this.loadProject());
        this.generateOutlineBtn.addEventListener("click", () => this.generateOutline());
        this.saveOutlineBtn.addEventListener("click", () => this.saveOutline());
        this.generateChapterBtn.addEventListener("click", () => this.generateChapter());
        this.saveChapterBtn.addEventListener("click", () => this.saveChapter());
        if (this.themeToggleBtn) {
            this.themeToggleBtn.addEventListener("click", () => this.toggleTheme());
        }
    }

    async initialize() {
        try {
            await this.loadHistoryProjects();
        } catch (error) {
            this.setStatus(error.message, true);
        }
    }

    getProjectParams() {
        const novelId = this.novelIdInput.value.trim();
        const title = this.novelTitleInput.value.trim();
        if (!novelId || !title) {
            throw new Error("请先填写小说 ID 和标题");
        }
        return { novelId, title };
    }

    setProjectInputs({ novelId, title }) {
        this.novelIdInput.value = novelId || "";
        this.novelTitleInput.value = title || "";
    }

    parseTags() {
        return this.novelTagsInput.value
            .split(/[,\uff0c]/)
            .map((item) => item.trim())
            .filter(Boolean);
    }

    parseStyleTags() {
        const result = {};
        this.styleTagsInput.value
            .split("\n")
            .map((line) => line.trim())
            .filter(Boolean)
            .forEach((line) => {
                const parts = line.split("=");
                if (parts.length >= 2) {
                    const key = parts.shift().trim();
                    const value = parts.join("=").trim();
                    if (key && value) {
                        result[key] = value;
                    }
                }
            });
        return result;
    }

    async loadProjectFromInput() {
        const { novelId, title } = this.getProjectParams();
        await this.loadProject({ novelId, title });
    }

    async loadProject(params = null, options = {}) {
        try {
            const resolved = params || this.getProjectParams();
            this.setProjectInputs(resolved);
            const payload = await this.request(
                `/projects/${encodeURIComponent(resolved.title)}/${encodeURIComponent(resolved.novelId)}`
            );
            this.project = payload.data || null;
            this.currentOutlineId = this.project?.outline_id || null;
            if (this.currentChapterId && !this.findChapterMeta(this.currentChapterId)) {
                this.clearChapterEditor();
            }
            this.renderProject();
            if (this.currentOutlineId) {
                await this.loadOutline(this.currentOutlineId);
            } else {
                this.clearOutlineEditor();
            }

            this.rememberCurrentProject();
            this.renderHistoryProjects();
            if (!options.silentStatus) {
                this.setStatus(`已加载项目 ${resolved.title} / ${resolved.novelId}`);
            }
        } catch (error) {
            this.setStatus(error.message, true);
        }
    }

    async loadHistoryProjects() {
        const payload = await this.request("/projects");
        this.historyProjects = payload.data?.projects || [];
        this.renderHistoryProjects();

        if (!this.historyProjects.length) {
            this.setStatus("暂无历史小说，可以先创建一个新项目。");
            return;
        }

        const lastProject = this.readRememberedProject();
        const preferredProject = this.historyProjects.find(
            (item) => item.novel_id === lastProject?.novelId && item.title === lastProject?.title
        );
        const projectToOpen = preferredProject || this.historyProjects[0];
        await this.loadProject(
            {
                novelId: projectToOpen.novel_id,
                title: projectToOpen.title,
            },
            { silentStatus: true }
        );
        this.setStatus(`已自动加载历史小说 ${projectToOpen.title} / ${projectToOpen.novel_id}`);
    }

    renderHistoryProjects() {
        if (!this.historyProjectList) {
            return;
        }
        if (!this.historyProjects.length) {
            this.historyProjectList.innerHTML = `<div class="empty-state">还没有历史小说。</div>`;
            return;
        }

        this.historyProjectList.innerHTML = "";
        this.historyProjects.forEach((project) => {
            const item = document.createElement("button");
            item.type = "button";
            item.className = "history-project-item";
            item.classList.toggle(
                "active",
                project.novel_id === this.project?.novel_id && project.title === this.project?.title
            );
            item.innerHTML = `
                <div class="history-project-title">
                    <strong>${this.escapeHtml(project.title || "未命名小说")}</strong>
                    <span class="history-project-meta">${this.escapeHtml(String(project.chapter_count || 0))} 章</span>
                </div>
                <div class="history-project-id">${this.escapeHtml(project.novel_id || "-")}</div>
                <div class="history-project-meta">更新于 ${this.escapeHtml(this.formatDate(project.updated_at))}</div>
            `;
            item.addEventListener("click", async () => {
                await this.loadProject({ novelId: project.novel_id, title: project.title });
            });
            this.historyProjectList.appendChild(item);
        });
    }

    rememberCurrentProject() {
        if (!this.project?.novel_id || !this.project?.title) {
            return;
        }
        localStorage.setItem(
            this.lastProjectStorageKey,
            JSON.stringify({ novelId: this.project.novel_id, title: this.project.title })
        );
    }

    readRememberedProject() {
        try {
            const raw = localStorage.getItem(this.lastProjectStorageKey);
            return raw ? JSON.parse(raw) : null;
        } catch (error) {
            return null;
        }
    }

    async generateOutline() {
        try {
            const { novelId, title } = this.getProjectParams();
            const userInput = this.outlineIdeaInput.value.trim();
            if (!userInput) {
                throw new Error("请先填写大纲创意");
            }

            this.outlineContentOutput.value = "";
            this.setGeneratingState(this.generateOutlineBtn, true, "生成中...");
            this.setStatus("正在流式生成大纲...");

            let generatedOutlineId = null;
            let fullContent = "";
            await this.streamRequest("/outline/generate_stream", {
                novel_id: novelId,
                title,
                user_input: userInput,
                tags: this.parseTags(),
                target_length: Number(this.targetLengthInput.value) || 3000,
                style_tags: this.parseStyleTags(),
            }, {
                onEvent: (payload) => {
                    if (payload.type === "content") {
                        fullContent += payload.data || "";
                        this.outlineContentOutput.value = fullContent;
                        this.scrollTextareaToBottom(this.outlineContentOutput);
                    } else if (payload.type === "done") {
                        generatedOutlineId = payload.data?.note_id || null;
                        fullContent = payload.data?.content || fullContent;
                        this.outlineContentOutput.value = fullContent;
                    } else if (payload.type === "error") {
                        throw new Error(payload.data || "大纲流式生成失败");
                    }
                },
            });

            this.currentOutlineId = generatedOutlineId;
            await this.refreshHistoryProjects();
            await this.loadProject({ novelId, title }, { silentStatus: true });
            this.setStatus("大纲生成完成");
        } catch (error) {
            this.setStatus(error.message, true);
        } finally {
            this.setGeneratingState(this.generateOutlineBtn, false, "生成大纲");
        }
    }

    async loadOutline(noteId) {
        const { novelId, title } = this.getProjectParams();
        const payload = await this.request(
            `/outline/${encodeURIComponent(title)}/${encodeURIComponent(novelId)}/${encodeURIComponent(noteId)}`
        );
        this.outlineContentOutput.value = payload.data?.content || "";
    }

    async saveOutline() {
        try {
            const { novelId, title } = this.getProjectParams();
            if (!this.currentOutlineId) {
                throw new Error("当前还没有可保存的大纲");
            }
            await this.request("/outline/update", {
                method: "PUT",
                body: JSON.stringify({
                    novel_id: novelId,
                    title,
                    note_id: this.currentOutlineId,
                    content: this.outlineContentOutput.value,
                    tags: this.parseTags(),
                }),
            });
            await this.refreshHistoryProjects();
            await this.loadProject({ novelId, title }, { silentStatus: true });
            this.setStatus("大纲已保存");
        } catch (error) {
            this.setStatus(error.message, true);
        }
    }

    async generateChapter() {
        try {
            const { novelId, title } = this.getProjectParams();
            if (!this.currentOutlineId) {
                throw new Error("请先生成或加载大纲，再生成章节");
            }

            this.clearChapterEditor();
            this.setGeneratingState(this.generateChapterBtn, true, "生成中...");
            this.setStatus("正在流式生成章节...");

            let latestChapter = null;
            let fullContent = "";
            await this.streamRequest("/chapter/generate_stream", {
                novel_id: novelId,
                title,
                user_input: this.chapterIdeaInput.value.trim(),
                num_chapters: Number(this.chapterCountInput.value) || 1,
                chapter_length: Number(this.chapterLengthInput.value) || 3000,
            }, {
                onEvent: (payload) => {
                    if (payload.type === "status") {
                        this.setStatus(payload.data || "正在生成章节...");
                    } else if (payload.type === "chapter_start") {
                        fullContent = "";
                        this.chapterContentOutput.value = "";
                    } else if (payload.type === "content") {
                        fullContent += payload.data || "";
                        this.chapterContentOutput.value = fullContent;
                        this.scrollTextareaToBottom(this.chapterContentOutput);
                    } else if (payload.type === "chapter_finalized") {
                        latestChapter = payload.data || latestChapter;
                        this.currentChapterId = latestChapter?.id || null;
                        this.chapterTitleInput.value = latestChapter?.title || "";
                        this.chapterSummaryInput.value = latestChapter?.summary || "";
                        this.chapterPredictionInput.value = latestChapter?.next_chapter_prediction || "";
                        this.chapterContentOutput.value = latestChapter?.content || fullContent;
                    } else if (payload.type === "chapter_done") {
                        latestChapter = payload.data || latestChapter;
                    } else if (payload.type === "error") {
                        throw new Error(payload.data || "章节流式生成失败");
                    }
                },
            });

            await this.refreshHistoryProjects();
            await this.loadProject({ novelId, title }, { silentStatus: true });
            if (latestChapter?.id) {
                await this.openChapter(latestChapter.id);
            }
            this.setStatus("章节生成完成");
        } catch (error) {
            this.setStatus(error.message, true);
        } finally {
            this.setGeneratingState(this.generateChapterBtn, false, "生成章节");
        }
    }

    async openChapter(noteId) {
        try {
            const { novelId, title } = this.getProjectParams();
            const payload = await this.request(
                `/chapter/${encodeURIComponent(title)}/${encodeURIComponent(novelId)}/${encodeURIComponent(noteId)}`
            );
            const chapter = payload.data || {};
            this.currentChapterId = noteId;
            this.chapterTitleInput.value = chapter.title || "";
            this.chapterSummaryInput.value = chapter.summary || "";
            this.chapterPredictionInput.value = this.findChapterMeta(noteId)?.next_chapter_prediction || "";
            this.chapterContentOutput.value = chapter.content || "";
            this.highlightActiveChapter();
        } catch (error) {
            this.setStatus(error.message, true);
        }
    }

    async saveChapter() {
        try {
            const { novelId, title } = this.getProjectParams();
            if (!this.currentChapterId) {
                throw new Error("请先选择一个章节");
            }
            await this.request("/chapter/update", {
                method: "PUT",
                body: JSON.stringify({
                    novel_id: novelId,
                    title,
                    note_id: this.currentChapterId,
                    content: this.chapterContentOutput.value,
                    chapter_title: this.chapterTitleInput.value,
                    summary: this.chapterSummaryInput.value,
                    next_chapter_prediction: this.chapterPredictionInput.value,
                }),
            });
            await this.refreshHistoryProjects();
            await this.loadProject({ novelId, title }, { silentStatus: true });
            await this.openChapter(this.currentChapterId);
            this.setStatus("章节已保存");
        } catch (error) {
            this.setStatus(error.message, true);
        }
    }

    renderProject() {
        if (!this.project) {
            this.projectMeta.innerHTML = `<div class="empty-state">还没有加载项目。</div>`;
            this.chapterList.innerHTML = `<div class="empty-state">还没有章节。</div>`;
            this.clearOutlineEditor();
            this.clearChapterEditor();
            return;
        }

        const metaItems = [
            ["标题", this.project.title || "-"],
            ["ID", this.project.novel_id || "-"],
            ["大纲", this.project.outline_id || "未生成"],
            ["章节数", String((this.project.chapters || []).length)],
            ["更新时间", this.formatDate(this.project.updated_at)],
        ];
        this.projectMeta.innerHTML = metaItems
            .map(
                ([label, value]) =>
                    `<div class="meta-item"><span>${this.escapeHtml(label)}</span><strong>${this.escapeHtml(value)}</strong></div>`
            )
            .join("");

        const chapters = this.project.chapters || [];
        if (!chapters.length) {
            this.chapterList.innerHTML = `<div class="empty-state">还没有章节。</div>`;
            this.clearChapterEditor();
            return;
        }

        this.chapterList.innerHTML = "";
        chapters.forEach((chapter, index) => {
            const item = document.createElement("button");
            item.className = "chapter-item";
            item.dataset.noteId = chapter.id;
            item.innerHTML = `
                <span class="chapter-index">${index + 1}</span>
                <span class="chapter-main">
                    <strong>${this.escapeHtml(chapter.title || chapter.id)}</strong>
                    <small>${this.escapeHtml(chapter.summary || "暂无摘要")}</small>
                </span>
            `;
            item.addEventListener("click", () => this.openChapter(chapter.id));
            this.chapterList.appendChild(item);
        });
        this.highlightActiveChapter();
    }

    highlightActiveChapter() {
        this.chapterList.querySelectorAll(".chapter-item").forEach((item) => {
            item.classList.toggle("active", item.dataset.noteId === this.currentChapterId);
        });
    }

    findChapterMeta(noteId) {
        return (this.project?.chapters || []).find((item) => item.id === noteId) || null;
    }

    clearOutlineEditor() {
        this.currentOutlineId = null;
        this.outlineContentOutput.value = "";
    }

    clearChapterEditor() {
        this.currentChapterId = null;
        this.chapterTitleInput.value = "";
        this.chapterSummaryInput.value = "";
        this.chapterPredictionInput.value = "";
        this.chapterContentOutput.value = "";
    }

    async refreshHistoryProjects() {
        const payload = await this.request("/projects");
        this.historyProjects = payload.data?.projects || [];
        this.renderHistoryProjects();
    }

    async streamRequest(path, body, { onEvent }) {
        const response = await fetch(`${this.apiBase}${path}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        if (!response.ok) {
            let payload = {};
            try {
                payload = await response.json();
            } catch (error) {
                payload = {};
            }
            throw new Error(this.formatApiError(payload, response.status));
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

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
                onEvent(JSON.parse(raw));
            }
        }
    }

    setGeneratingState(button, loading, idleText) {
        if (!button) {
            return;
        }
        button.disabled = loading;
        button.textContent = loading ? "生成中..." : idleText;
    }

    scrollTextareaToBottom(node) {
        if (!node) {
            return;
        }
        node.scrollTop = node.scrollHeight;
    }

    formatDate(value) {
        if (!value) {
            return "-";
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return value;
        }
        return date.toLocaleString();
    }

    applyStoredTheme() {
        const stored = localStorage.getItem(this.themeStorageKey);
        const theme = stored === "light" ? "light" : "dark";
        document.body.dataset.theme = theme;
        this.updateThemeToggleLabel(theme);
    }

    toggleTheme() {
        const current = document.body.dataset.theme === "light" ? "light" : "dark";
        const next = current === "light" ? "dark" : "light";
        document.body.dataset.theme = next;
        localStorage.setItem(this.themeStorageKey, next);
        this.updateThemeToggleLabel(next);
    }

    updateThemeToggleLabel(theme) {
        if (!this.themeToggleBtn) {
            return;
        }
        this.themeToggleBtn.textContent = theme === "light" ? "深色模式" : "浅色模式";
    }

    setStatus(message, isError = false) {
        this.novelStatusText.textContent = message;
        this.novelStatusText.classList.toggle("error-text", isError);
    }

    async request(path, options = {}) {
        const headers = { ...(options.headers || {}) };
        if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
            headers["Content-Type"] = "application/json";
        }

        const response = await fetch(`${this.apiBase}${path}`, {
            ...options,
            headers,
        });
        const raw = await response.text();
        let payload = {};
        try {
            payload = raw ? JSON.parse(raw) : {};
        } catch (error) {
            payload = { detail: raw || "Invalid JSON response" };
        }
        if (!response.ok) {
            throw new Error(this.formatApiError(payload, response.status));
        }
        return payload;
    }

    formatApiError(payload, status) {
        if (Array.isArray(payload?.detail)) {
            return payload.detail
                .map((item) => {
                    const location = Array.isArray(item?.loc) ? item.loc.join(".") : "request";
                    const message = item?.msg || "Invalid request";
                    return `${location}: ${message}`;
                })
                .join(" | ");
        }
        if (typeof payload?.detail === "string" && payload.detail.trim()) {
            return payload.detail;
        }
        if (typeof payload?.message === "string" && payload.message.trim()) {
            return payload.message;
        }
        return `HTTP ${status}`;
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
    new NovelStudioApp();
});
