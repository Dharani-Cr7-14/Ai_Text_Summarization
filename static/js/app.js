const form = document.getElementById("summarizeForm");
const summarizeBtn = document.getElementById("summarizeBtn");
const loadingSpinner = document.getElementById("loadingSpinner");
const loadingText = document.getElementById("loadingText");
const summaryOutput = document.getElementById("summaryOutput");
const errorBox = document.getElementById("errorBox");
const originalCount = document.getElementById("originalCount");
const summaryCount = document.getElementById("summaryCount");
const compression = document.getElementById("compression");
const copyBtn = document.getElementById("copyBtn");
const downloadBtn = document.getElementById("downloadBtn");
const voiceBtn = document.getElementById("voiceBtn");
const themeToggle = document.getElementById("themeToggle");
const sidebarHistoryList = document.getElementById("sidebarHistoryList");
const historySearchInput = document.getElementById("historySearchInput");
const historySearchClear = document.getElementById("historySearchClear");

let latestSummary = "";
let latestKeyPoints = [];
let speechUtterance = null;

function formatSummaryForDisplay(summary) {
    if (!summary) {
        return "";
    }

    const normalized = summary.replace(/\s+/g, " ").trim();
    if (!normalized) {
        return "";
    }

    const sentences = normalized.split(/(?<=[.!?])\s+/).filter(Boolean);
    const chunks = [];
    for (let i = 0; i < sentences.length; i += 2) {
        chunks.push(sentences.slice(i, i + 2).join(" "));
    }
    return chunks.join("\n\n");
}

function escapeHtml(text) {
    return (text || "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function renderAnalysis(summary, keyPoints) {
    const safeSummary = escapeHtml(formatSummaryForDisplay(summary));
    const points = Array.isArray(keyPoints) ? keyPoints.filter(Boolean) : [];

    if (!summary) {
        summaryOutput.textContent = "Generated summary and key points will appear here...";
        return;
    }

    const pointsHtml = points.length
        ? `<ul class="mb-0 ps-3">${points.map((point) => `<li class="mb-2">${escapeHtml(point)}</li>`).join("")}</ul>`
        : "<p class=\"mb-0\">No key points found.</p>";

    summaryOutput.innerHTML = `
        <div class="fw-semibold mb-2">Summary</div>
        <p class="mb-3">${safeSummary.replaceAll("\n", "<br>")}</p>
        <div class="fw-semibold mb-2">Key Points</div>
        ${pointsHtml}
    `;
}

function getSpeechText() {
    if (!latestSummary) {
        return "";
    }
    const points = latestKeyPoints.length
        ? latestKeyPoints.map((point, index) => `Point ${index + 1}. ${point}.`).join(" ")
        : "";
    return `${latestSummary}. ${points}`.trim();
}

function stopSpeaking() {
    if (window.speechSynthesis.speaking) {
        window.speechSynthesis.cancel();
    }
    speechUtterance = null;
    voiceBtn.textContent = "Read Aloud";
}

function getCsrfToken() {
    const cookie = document.cookie
        .split(";")
        .map((item) => item.trim())
        .find((item) => item.startsWith("csrftoken="));
    return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
}

function setLoading(loading) {
    summarizeBtn.disabled = loading;
    loadingSpinner.classList.toggle("d-none", !loading);
    loadingText.classList.toggle("d-none", !loading);
}

function showError(message) {
    errorBox.textContent = message;
    errorBox.classList.remove("d-none");
}

function hideError() {
    errorBox.textContent = "";
    errorBox.classList.add("d-none");
}

function updateHistoryBadge() {
    const badge = document.getElementById("historyBadgeCount");
    if (!badge || !sidebarHistoryList) return;
    const count = sidebarHistoryList.querySelectorAll(".shi.history-row").length;
    badge.textContent = count;
}

function getHistorySearchText(row) {
    if (!row) return "";
    const combined = [
        row.dataset.source,
        row.dataset.length,
        row.dataset.timestamp,
        row.dataset.original,
        row.dataset.summaryWords,
        row.dataset.compression,
        row.dataset.summary,
    ].join(" ");
    return combined.toLowerCase();
}

function applyHistorySearchFilter() {
    if (!sidebarHistoryList) return;

    const query = (historySearchInput?.value || "").trim().toLowerCase();
    const rows = sidebarHistoryList.querySelectorAll(".shi.history-row");
    let visibleCount = 0;

    rows.forEach((row) => {
        const searchable = row.dataset.searchText || getHistorySearchText(row);
        row.dataset.searchText = searchable;
        const matched = !query || searchable.includes(query);
        row.classList.toggle("d-none", !matched);
        if (matched) visibleCount += 1;
    });

    const existingNoResult = sidebarHistoryList.querySelector(".shi-search-empty");
    if (existingNoResult) existingNoResult.remove();

    if (query && rows.length > 0 && visibleCount === 0) {
        const noResult = document.createElement("div");
        noResult.className = "shi-search-empty";
        noResult.textContent = "No history found for this keyword.";
        sidebarHistoryList.append(noResult);
    }
}

function addHistoryRow(data, source = "Text", length = "Medium") {
    if (!sidebarHistoryList) return;
    const emptyEl = sidebarHistoryList.querySelector(".shi-empty");
    if (emptyEl) emptyEl.remove();

    const timestamp = new Date().toISOString().slice(0, 16).replace("T", " ");
    const timeOnly = timestamp.slice(11, 16);
    const dateOnly = new Date().toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

    const row = document.createElement("div");
    row.className = "shi history-row";
    row.style.cursor = "pointer";
    row.dataset.summary = data.summary || "";
    row.dataset.timestamp = timestamp;
    row.dataset.source = source;
    row.dataset.length = length;
    row.dataset.original = data.original_word_count;
    row.dataset.summaryWords = data.summary_word_count;
    row.dataset.compression = data.compression_percentage;
    row.dataset.searchText = `${source} ${length} ${timestamp} ${data.original_word_count} ${data.summary_word_count} ${data.compression_percentage} ${data.summary || ""}`.toLowerCase();
    row.innerHTML = `
        <div class="shi-row1">
            <span class="shi-source">${escapeHtml(source)}</span>
            <span class="shi-time">${timeOnly}</span>
        </div>
        <div class="shi-row2">${escapeHtml(length)} &middot; ${data.original_word_count}&rarr;${data.summary_word_count}w &middot; ${data.compression_percentage}%</div>
        <div class="shi-date">${dateOnly}</div>
    `;
    sidebarHistoryList.prepend(row);

    // keep at most 10 items
    const items = sidebarHistoryList.querySelectorAll(".shi.history-row");
    if (items.length > 10) items[items.length - 1].remove();

    updateHistoryBadge();
    applyHistorySearchFilter();
}

if (historySearchInput) {
    historySearchInput.addEventListener("input", applyHistorySearchFilter);
    historySearchInput.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            historySearchInput.value = "";
            applyHistorySearchFilter();
        }
    });
}

if (historySearchClear) {
    historySearchClear.addEventListener("click", () => {
        if (!historySearchInput) return;
        historySearchInput.value = "";
        applyHistorySearchFilter();
        historySearchInput.focus();
    });
}

// History row click → show summary modal
if (sidebarHistoryList) sidebarHistoryList.addEventListener("click", (e) => {
    const row = e.target.closest(".history-row");
    if (!row) return;

    const summary = row.dataset.summary || "";
    const timestamp = row.dataset.timestamp || "";
    const source = row.dataset.source || "";
    const length = row.dataset.length || "";
    const original = row.dataset.original || "0";
    const summaryWords = row.dataset.summaryWords || "0";
    const comp = row.dataset.compression || "0";

    document.getElementById("historyModalMeta").innerHTML = `
        <span class="badge text-bg-secondary">${escapeHtml(timestamp)}</span>
        <span class="badge text-bg-primary">${escapeHtml(source)}</span>
        <span class="badge text-bg-info text-dark">${escapeHtml(length)}</span>
        <span class="badge text-bg-light border text-dark">${original} → ${summaryWords} words · ${comp}% compression</span>
    `;

    const formatted = formatSummaryForDisplay(summary);
    document.getElementById("historyModalSummaryText").innerHTML =
        escapeHtml(formatted).replaceAll("\n\n", "<br><br>");

    const copyBtn = document.getElementById("historyModalCopyBtn");
    copyBtn.textContent = "Copy";
    copyBtn.onclick = async () => {
        await navigator.clipboard.writeText(summary);
        copyBtn.textContent = "Copied!";
        setTimeout(() => { copyBtn.textContent = "Copy"; }, 1200);
    };

    new bootstrap.Modal(document.getElementById("historyModal")).show();
});

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    hideError();
    if ("speechSynthesis" in window && window.speechSynthesis.speaking) {
        stopSpeaking();
    }
    setLoading(true);

    try {
        const formData = new FormData(form);
        const response = await fetch("/summarize/", {
            method: "POST",
            headers: {
                "X-CSRFToken": getCsrfToken(),
            },
            body: formData,
        });

        const result = await response.json();
        if (!response.ok || !result.ok) {
            throw new Error(result.error || "Failed to summarize text.");
        }

        const data = result.data;
        latestSummary = data.summary;
        latestKeyPoints = Array.isArray(data.key_points) ? data.key_points : [];
        renderAnalysis(data.summary, latestKeyPoints);
        originalCount.textContent = data.original_word_count;
        summaryCount.textContent = data.summary_word_count;
        compression.textContent = `${data.compression_percentage}%`;
        copyBtn.disabled = false;
        downloadBtn.disabled = false;
        voiceBtn.disabled = false;

        const lengthSelect = document.getElementById("lengthSelect");
        const selectedLength = lengthSelect.options[lengthSelect.selectedIndex].text;

        const source = formData.get("text")
            ? "Text"
            : formData.get("url")
                ? "URL"
                : "PDF";

        addHistoryRow(data, source, selectedLength);
    } catch (error) {
        showError(error.message || "Unexpected error occurred.");
    } finally {
        setLoading(false);
    }
});

copyBtn.addEventListener("click", async () => {
    if (!latestSummary) {
        return;
    }

    const pointsText = latestKeyPoints.length
        ? `\n\nKey Points:\n${latestKeyPoints.map((point) => `- ${point}`).join("\n")}`
        : "";
    await navigator.clipboard.writeText(`Summary:\n${latestSummary}${pointsText}`);
    copyBtn.textContent = "Copied!";
    setTimeout(() => {
        copyBtn.textContent = "Copy";
    }, 1200);
});

downloadBtn.addEventListener("click", () => {
    if (!latestSummary) {
        return;
    }
    const pointsText = latestKeyPoints.length
        ? `\n\nKey Points:\n${latestKeyPoints.map((point) => `- ${point}`).join("\n")}`
        : "";
    const downloadable = `Summary:\n${latestSummary}${pointsText}`;
    const targetUrl = `/download-summary/?summary=${encodeURIComponent(downloadable)}`;
    window.location.href = targetUrl;
});

voiceBtn.addEventListener("click", () => {
    if (!latestSummary || !("speechSynthesis" in window)) {
        return;
    }

    if (window.speechSynthesis.speaking) {
        stopSpeaking();
        return;
    }

    const speechText = getSpeechText();
    if (!speechText) {
        return;
    }

    speechUtterance = new SpeechSynthesisUtterance(speechText);
    speechUtterance.rate = 0.95;
    speechUtterance.pitch = 1;
    speechUtterance.onend = () => {
        speechUtterance = null;
        voiceBtn.textContent = "Read Aloud";
    };
    speechUtterance.onerror = () => {
        speechUtterance = null;
        voiceBtn.textContent = "Read Aloud";
    };

    voiceBtn.textContent = "Stop Reading";
    window.speechSynthesis.speak(speechUtterance);
});

function applyTheme(theme) {
    document.documentElement.setAttribute("data-bs-theme", theme);
    localStorage.setItem("theme", theme);
}

const initialTheme = localStorage.getItem("theme") || "light";
applyTheme(initialTheme);

if (!("speechSynthesis" in window)) {
    voiceBtn.disabled = true;
    voiceBtn.textContent = "Voice Unavailable";
}

themeToggle.addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-bs-theme");
    applyTheme(current === "light" ? "dark" : "light");
});

// Auto-resize the ChatGPT-style textarea
const cgptTextarea = document.getElementById("textInput");
if (cgptTextarea) {
    cgptTextarea.addEventListener("input", () => {
        cgptTextarea.style.height = "auto";
        cgptTextarea.style.height = Math.min(cgptTextarea.scrollHeight, 200) + "px";
    });
}

// ---- + button popup menu ----
const cgptPlusBtn  = document.getElementById("cgptPlusBtn");
const cgptPlusMenu = document.getElementById("cgptPlusMenu");
const menuPdfBtn   = document.getElementById("menuPdfBtn");
const menuUrlBtn   = document.getElementById("menuUrlBtn");

function closePlusMenu() {
    cgptPlusMenu.classList.remove("open");
    cgptPlusBtn.classList.remove("active");
    cgptPlusBtn.setAttribute("aria-expanded", "false");
}

cgptPlusBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    const isOpen = cgptPlusMenu.classList.contains("open");
    if (isOpen) {
        closePlusMenu();
    } else {
        cgptPlusMenu.classList.add("open");
        cgptPlusBtn.classList.add("active");
        cgptPlusBtn.setAttribute("aria-expanded", "true");
    }
});

// Upload PDF option — trigger the hidden file input
if (menuPdfBtn) {
    menuPdfBtn.addEventListener("click", () => {
        closePlusMenu();
        const pdfField = document.getElementById("pdfInput");
        if (pdfField) pdfField.click();
    });
}

// Enter URL option — show / hide the inline URL bar
const cgptUrlBar  = document.getElementById("cgptUrlBar");
const cgptUrlClear = document.getElementById("cgptUrlClear");
const urlInputField = document.getElementById("urlInput");

if (menuUrlBtn) {
    menuUrlBtn.addEventListener("click", () => {
        closePlusMenu();
        if (cgptUrlBar) {
            const isVisible = !cgptUrlBar.classList.contains("d-none");
            if (isVisible) {
                cgptUrlBar.classList.add("d-none");
                if (urlInputField) urlInputField.value = "";
            } else {
                cgptUrlBar.classList.remove("d-none");
                if (urlInputField) {
                    urlInputField.focus();
                    urlInputField.select();
                }
            }
        }
    });
}

// × button clears and hides the inline URL bar
if (cgptUrlClear) {
    cgptUrlClear.addEventListener("click", () => {
        if (cgptUrlBar) cgptUrlBar.classList.add("d-none");
        if (urlInputField) urlInputField.value = "";
    });
}

// Close menu when clicking outside
document.addEventListener("click", (e) => {
    if (cgptPlusMenu && !cgptPlusMenu.contains(e.target) && e.target !== cgptPlusBtn) {
        closePlusMenu();
    }
});

// Close menu on Escape key
document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closePlusMenu();
});

// ---- Sidebar ----
(function initSidebar() {
    const appLayout = document.querySelector(".app-layout");
    const sidebar  = document.getElementById("appSidebar");
    const backdrop = document.getElementById("sidebarBackdrop");
    const toggler  = document.getElementById("sidebarToggler");
    const desktopQuery = window.matchMedia ? window.matchMedia("(min-width: 992px)") : null;

    function isDesktop() {
        if (desktopQuery) return desktopQuery.matches;
        return window.innerWidth >= 992;
    }

    function readCollapsedPref() {
        try {
            return localStorage.getItem("sidebar-collapsed") === "1";
        } catch (_) {
            return false;
        }
    }

    function writeCollapsedPref(isCollapsed) {
        try {
            localStorage.setItem("sidebar-collapsed", isCollapsed ? "1" : "0");
        } catch (_) {
            // ignore storage errors (private mode / browser restrictions)
        }
    }

    function setTogglerExpanded(isExpanded) {
        if (!toggler) return;
        toggler.setAttribute("aria-expanded", isExpanded ? "true" : "false");
    }

    function openSidebar() {
        if (!sidebar) return;
        sidebar.classList.add("sidebar-open");
        if (backdrop) backdrop.classList.add("show");
        document.body.style.overflow = "hidden";
        setTogglerExpanded(true);
    }

    function closeSidebar() {
        if (!sidebar) return;
        sidebar.classList.remove("sidebar-open");
        if (backdrop) backdrop.classList.remove("show");
        document.body.style.overflow = "";
        setTogglerExpanded(false);
    }

    function applyDesktopCollapsed(isCollapsed) {
        if (!appLayout) return;
        appLayout.classList.toggle("sidebar-collapsed", isCollapsed);
        setTogglerExpanded(!isCollapsed);
        writeCollapsedPref(isCollapsed);
    }

    function toggleSidebar() {
        if (!sidebar) return;

        if (isDesktop()) {
            const collapsed = appLayout ? appLayout.classList.contains("sidebar-collapsed") : false;
            applyDesktopCollapsed(!collapsed);
            return;
        }

        sidebar.classList.contains("sidebar-open") ? closeSidebar() : openSidebar();
    }

    function syncSidebarMode() {
        if (isDesktop()) {
            closeSidebar();
            const saved = readCollapsedPref();
            applyDesktopCollapsed(saved);
        } else {
            if (appLayout) appLayout.classList.remove("sidebar-collapsed");
            closeSidebar();
        }
    }

    if (toggler) {
        toggler.addEventListener("click", toggleSidebar);
    }
    if (backdrop) backdrop.addEventListener("click", closeSidebar);

    if (desktopQuery) {
        if (typeof desktopQuery.addEventListener === "function") {
            desktopQuery.addEventListener("change", syncSidebarMode);
        } else if (typeof desktopQuery.addListener === "function") {
            desktopQuery.addListener(syncSidebarMode);
        }
    } else {
        window.addEventListener("resize", syncSidebarMode);
    }
    syncSidebarMode();

    // New Summary → focus textarea
    const snavNewSummary = document.getElementById("snavNewSummary");
    if (snavNewSummary) {
        snavNewSummary.addEventListener("click", () => {
            closeSidebar();
            const ta = document.getElementById("textInput");
            if (ta) { ta.focus(); ta.scrollIntoView({ behavior: "smooth", block: "center" }); }
        });
    }

    // Search → focus input and select text for quick editing/searching
    const snavSearch = document.getElementById("snavSearch");
    if (snavSearch) {
        snavSearch.addEventListener("click", () => {
            if (historySearchInput) {
                historySearchInput.scrollIntoView({ behavior: "smooth", block: "center" });
                historySearchInput.focus();
                historySearchInput.select();
            }
        });
    }

    // History → flash the history list
    const snavHistory = document.getElementById("snavHistory");
    if (snavHistory) {
        snavHistory.addEventListener("click", () => {
            const list = document.getElementById("sidebarHistoryList");
            if (!list) return;
            list.scrollIntoView({ behavior: "smooth", block: "nearest" });
            list.style.outline = "2px solid rgba(var(--bs-primary-rgb),0.55)";
            list.style.borderRadius = "0.5rem";
            setTimeout(() => { list.style.outline = ""; list.style.borderRadius = ""; }, 900);
        });
    }

    // Dark Mode toggle from sidebar
    const snavTheme = document.getElementById("snavTheme");
    if (snavTheme) {
        snavTheme.addEventListener("click", () => {
            const cur = document.documentElement.getAttribute("data-bs-theme");
            applyTheme(cur === "light" ? "dark" : "light");
        });
    }

    // About
    const snavAbout = document.getElementById("snavAbout");
    if (snavAbout) {
        snavAbout.addEventListener("click", () => {
            alert(
                "AI Text Summarizer\n\n" +
                "Powered by BART-Large-CNN (HuggingFace Transformers) and Django 5.\n\n" +
                "Features:\n" +
                "• Text, URL & PDF summarization\n" +
                "• Short, Medium, and Detailed lengths\n" +
                "• Speech-to-text dictation (Web Speech API)\n" +
                "• Read Aloud text-to-speech output\n" +
                "• Real-time AJAX — no page reload"
            );
        });
    }

    // Init badge count from server-rendered items
    updateHistoryBadge();
    applyHistorySearchFilter();
}());

// ---- Dictation (Speech-to-Text) ----
(function initDictation() {
    const dictateBtn = document.getElementById("dictateBtn");
    if (!dictateBtn) return;

    const SpeechRecognition =
        window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
        dictateBtn.classList.add("dictate-unsupported");
        dictateBtn.title = "Speech recognition not supported in this browser";
        return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = true;      // keep listening until stopped
    recognition.interimResults = true;  // show partial results while speaking
    recognition.lang = "en-US";

    let isListening = false;
    let interimStart = 0; // character offset where interim text begins

    function startDictation() {
        isListening = true;
        dictateBtn.classList.add("recording");
        dictateBtn.setAttribute("aria-label", "Stop dictation");
        dictateBtn.title = "Stop dictation";
        // Record where in the textarea we start appending
        const ta = document.getElementById("textInput");
        interimStart = ta ? ta.value.length : 0;
        recognition.start();
    }

    function stopDictation() {
        isListening = false;
        recognition.stop();
        dictateBtn.classList.remove("recording");
        dictateBtn.setAttribute("aria-label", "Start dictation");
        dictateBtn.title = "Dictate";
    }

    dictateBtn.addEventListener("click", () => {
        if (isListening) {
            stopDictation();
        } else {
            startDictation();
        }
    });

    recognition.addEventListener("result", (event) => {
        const ta = document.getElementById("textInput");
        if (!ta) return;

        let interimTranscript = "";
        let finalTranscript = "";

        for (let i = event.resultIndex; i < event.results.length; i++) {
            const result = event.results[i];
            if (result.isFinal) {
                finalTranscript += result[0].transcript;
            } else {
                interimTranscript += result[0].transcript;
            }
        }

        // Keep any text typed before dictation started, then append
        const base = ta.value.slice(0, interimStart);
        ta.value = base + finalTranscript + interimTranscript;

        // If a final result was committed, advance the base offset
        if (finalTranscript) {
            interimStart = base.length + finalTranscript.length;
        }

        // Auto-resize
        ta.style.height = "auto";
        ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
    });

    recognition.addEventListener("end", () => {
        // If the engine stops on its own (e.g. silence timeout), restart
        // unless the user explicitly stopped
        if (isListening) {
            recognition.start();
        }
    });

    recognition.addEventListener("error", (event) => {
        // Ignore no-speech events — they are normal during pauses
        if (event.error === "no-speech") return;
        stopDictation();
        if (event.error === "not-allowed" || event.error === "service-not-allowed") {
            alert("Microphone access was denied. Please allow microphone permission in your browser and try again.");
        }
    });
}());