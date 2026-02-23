/**
 * Journal Agent - Web Interface JavaScript
 */

// State
const state = {
    ws: null,
    connected: false,
    displayMode: 'conversation', // 'conversation' or 'full'
    messages: [],
    isThinking: false,
    isStreaming: false,  // Track if currently receiving streaming tokens
    streamingContent: '',  // Accumulate streaming content
    theme: localStorage.getItem('theme') || 'light',
    // Debug/stats state with timestamps
    sessionStartTime: Date.now(),
    turnCount: 0,
    // Thread state
    currentThreadId: null,
    currentThreadTitle: 'New Conversation',
    currentThreadEmoji: null,  // Thread emoji icon
    threads: [],
    threadsVisible: false,
    threadHasMessages: false,
    
    // Per-tile state
    tiles: {
        chat: {
            model: 'openai/gpt-5-nano',
            filter: 'thread',
            usage: { input_tokens: 0, output_tokens: 0, cost: 0, calls: 0 }
        },
        distill: {
            model: 'gpt-5-nano',
            filter: 'thread',
            usage: { input_tokens: 0, output_tokens: 0, cost: 0, calls: 0 }
        }
    }
};

// Models loaded from backend (populated by fetchModels)
let MODELS = {};
let TOKEN_PRICING = {};

// User-friendly error messages
const ERROR_MESSAGES = {
    'Agent not initialized': 'The agent is still starting up. Please wait a moment and try again.',
    'WebSocket disconnected': 'Connection lost. Reconnecting...',
    'Failed to fetch': 'Unable to connect to the server. Please check if the server is running.',
    'No API key': 'API key not configured for this model. Please set up your API keys.',
    'rate limit': 'Rate limit exceeded. Please wait a moment before trying again.',
    'timeout': 'Request timed out. Please try again.',
    "'dict' object has no attribute": 'This model is not supported. Please select a different model.',
    'object has no attribute': 'This model returned an unexpected response format. Try a different model.',
    'not supported': 'This model is not supported. Please select a different model.',
};

// DOM Elements (populated after DOMContentLoaded)
let elements = {};

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    // Populate elements after DOM is ready
    elements = {
        leftSidebar: document.getElementById('leftSidebar'),
        toolsList: document.getElementById('toolsList'),
        chatMessages: document.getElementById('chatMessages'),
        messageInput: document.getElementById('messageInput'),
        sendBtn: document.getElementById('sendBtn'),
        thinkingIndicator: document.getElementById('thinkingIndicator'),
        connectionStatus: document.getElementById('connectionStatus'),
    };
    initializeTheme();
    initializeIcons();
    setupEventListeners();
    initializeResizers();
    loadUsageData(); // Restore usage data from localStorage
    await fetchModels(); // Fetch models from backend before rendering
    await fetchDistillationModels(); // Fetch distillation models
    connectWebSocket();
    loadTools();
    renderChatModelSelector();
    renderDistillModelSelector();
    loadDebugInfo();
    // Load thread info first - this will also update usage displays with correct threadId
    await loadCurrentThreadInfo();
});

// Fetch models from backend
async function fetchModels() {
    try {
        const response = await fetch('/api/models');
        const data = await response.json();
        
        // Build MODELS and TOKEN_PRICING from backend response
        MODELS = {};
        TOKEN_PRICING = {};
        
        for (const m of data.models) {
            MODELS[m.name] = { provider: m.provider, model: m.model };
            TOKEN_PRICING[m.model] = m.pricing || { input: 0, output: 0 };
        }
        
        // Set current model from backend
        if (data.current) {
            state.tiles.chat.model = `${data.current.provider}/${data.current.model}`;
        }
        
        console.log('Models loaded from backend:', Object.keys(MODELS));
    } catch (error) {
        console.error('Failed to fetch models:', error);
        // Fallback to defaults
        MODELS = {
            'Claude': { provider: 'claude', model: 'claude-sonnet-4-20250514' },
            'Mock': { provider: 'mock', model: 'mock-default' },
        };
        TOKEN_PRICING = {
            'claude-sonnet-4-20250514': { input: 3, output: 15 },
            'mock-default': { input: 0, output: 0 },
        };
    }
}

// Initialize theme
function initializeTheme() {
    document.documentElement.setAttribute('data-theme', state.theme);
    updateThemeIcon();
}

function toggleTheme() {
    state.theme = state.theme === 'light' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', state.theme);
    localStorage.setItem('theme', state.theme);
    updateThemeIcon();
}

function updateThemeIcon() {
    const lightIcon = document.getElementById('themeIconLight');
    const darkIcon = document.getElementById('themeIconDark');
    if (state.theme === 'dark') {
        lightIcon.style.display = 'none';
        darkIcon.style.display = 'block';
    } else {
        lightIcon.style.display = 'block';
        darkIcon.style.display = 'none';
    }
}

// Initialize Lucide icons
function initializeIcons() {
    lucide.createIcons();
}

// Setup event listeners
function setupEventListeners() {
    // Sidebar toggles
    document.getElementById('toggleLeftSidebar').addEventListener('click', () => {
        elements.leftSidebar.classList.toggle('collapsed');
    });
    
    // MCP pane toggle
    document.getElementById('toggleMcpPane').addEventListener('click', () => {
        document.getElementById('mcpPane').classList.toggle('collapsed');
    });
    
    // Theme toggle
    document.getElementById('themeToggle').addEventListener('click', toggleTheme);
    
    // Chat model selector (no longer locked to thread)
    document.getElementById('chatModelBtn')?.addEventListener('click', (e) => {
        e.stopPropagation();
        document.getElementById('chatModelDropdown').classList.toggle('visible');
    });
    
    // Distillation model selector
    document.getElementById('distillModelBtn')?.addEventListener('click', (e) => {
        e.stopPropagation();
        document.getElementById('distillModelDropdown').classList.toggle('visible');
    });
    
    // Close dropdowns when clicking outside
    document.addEventListener('click', () => {
        document.getElementById('chatModelDropdown')?.classList.remove('visible');
        document.getElementById('distillModelDropdown')?.classList.remove('visible');
    });
    
    // Tile filter buttons
    document.querySelectorAll('.tile-filters .filter-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const tile = e.target.closest('.tile-filters').dataset.tile;
            const filter = e.target.dataset.filter;
            setTileFilter(tile, filter);
        });
    });
    
    // Chat input
    elements.messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    
    elements.messageInput.addEventListener('input', () => {
        autoResizeTextarea();
    });
    
    elements.sendBtn.addEventListener('click', sendMessage);
    
    // Clear chat
    document.getElementById('clearChat').addEventListener('click', clearChat);
    
    // Refresh buttons
    document.getElementById('refreshTools').addEventListener('click', loadTools);
    
    // Thread management
    document.getElementById('toggleThreads').addEventListener('click', toggleThreadsDrawer);
    document.getElementById('closeThreads').addEventListener('click', () => {
        document.getElementById('threadsDrawer').classList.remove('visible');
        state.threadsVisible = false;
    });
    document.getElementById('newThread').addEventListener('click', createNewThread);
    document.getElementById('threadSearch').addEventListener('input', (e) => {
        filterThreads(e.target.value);
    });
    
    // Thread title input - save on blur or Enter
    const threadTitleInput = document.getElementById('currentThreadTitle');
    threadTitleInput.addEventListener('blur', () => saveThreadTitle());
    threadTitleInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            threadTitleInput.blur(); // This triggers the blur handler
        }
        if (e.key === 'Escape') {
            // Revert to saved title
            threadTitleInput.value = state.currentThreadTitle;
            threadTitleInput.blur();
        }
    });
    
    // Emoji picker setup
    setupEmojiPicker();
    
    // Global keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Ctrl+N - New thread
        if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
            e.preventDefault();
            createNewThread();
        }
    });
}

// Auto-resize textarea
function autoResizeTextarea() {
    const textarea = elements.messageInput;
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 150) + 'px';
}

// WebSocket connection
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/chat`;
    
    state.ws = new WebSocket(wsUrl);
    
    state.ws.onopen = () => {
        state.connected = true;
        updateConnectionStatus(true);
        console.log('WebSocket connected');
    };
    
    state.ws.onclose = () => {
        state.connected = false;
        updateConnectionStatus(false);
        console.log('WebSocket disconnected');
        // Reconnect after 3 seconds
        setTimeout(connectWebSocket, 3000);
    };
    
    state.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
    
    state.ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleWebSocketMessage(data);
    };
}

function updateConnectionStatus(connected) {
    const statusEl = elements.connectionStatus;
    if (!statusEl) return; // Element might not exist
    
    if (connected) {
        statusEl.classList.add('connected');
        statusEl.innerHTML = '<i data-lucide="wifi"></i>';
    } else {
        statusEl.classList.remove('connected');
        statusEl.innerHTML = '<i data-lucide="wifi-off"></i>';
    }
    lucide.createIcons();
}

function handleWebSocketMessage(data) {
    switch (data.type) {
        case 'thinking':
            setThinking(data.status);
            break;
        
        case 'thinking_message':
            // Real-time thinking/tool_execution message from LLM
            // msg_type is 'thinking' (has content) or 'tool_execution' (just tools)
            addThinkingMessage(data.content, data.tool_calls || [], data.msg_type);
            break;
        
        case 'stream_token':
            // Streaming token from LLM
            handleStreamToken(data.token);
            break;
        
        case 'stream_end':
            // End of streaming - finalize the message
            handleStreamEnd();
            break;
        
        case 'stream_cancel':
            // Cancel streaming - this was a tool-calling response, not final
            // It will be shown as a thinking message instead
            handleStreamCancel();
            break;
            
        case 'response':
            state.turnCount++;
            // Only add message if we didn't already stream it
            // (the last message would be our finalized streaming message)
            const lastMsg = state.messages[state.messages.length - 1];
            const alreadyStreamed = lastMsg && 
                                    lastMsg.role === 'assistant' && 
                                    lastMsg.type === 'response' &&
                                    lastMsg.content === data.content;
            if (!alreadyStreamed) {
                addAssistantMessage(data.content, data.tool_calls || []);
            }
            // Update thread info FIRST (before tracking usage)
            if (data.thread_id) {
                state.currentThreadId = data.thread_id;
            }
            if (data.thread_title) {
                updateThreadTitle(data.thread_title);
            }
            // Refresh tool usage from backend (tools are logged server-side)
            if (data.tool_calls && data.tool_calls.length > 0) {
                loadToolUsage();
            }
            // Track token usage
            if (data.usage) {
                trackTokenUsage(data.usage);
            }
            updateDebugDisplay();
            break;
            
        case 'debug':
            // Tool usage is tracked server-side, just refresh display
            if (data.tool_calls && data.tool_calls.length > 0) {
                loadToolUsage();
            }
            break;
            
        case 'debug_full':
            updateFullDebugInfo(data);
            break;
        
        case 'log_entry':
            // Real-time log entry from backend
            handleLogEntry(data.entry);
            break;
            
        case 'tools':
            renderTools(data.servers);
            break;
            
        case 'error':
            addErrorMessage(data.error);
            break;
        
        // Thread events
        case 'threads':
            state.threads = data.threads || [];
            state.currentThreadId = data.current_thread_id;
            renderThreadsList();
            break;
            
        case 'thread_created':
            state.currentThreadId = data.thread_id;
            updateThreadTitle(data.title);
            state.messages = [];
            renderMessages();
            showToast('New conversation started');
            loadThreads(); // Refresh list
            break;
            
        case 'thread_loaded':
            state.currentThreadId = data.thread_id;
            updateThreadTitle(data.title);
            // Restore messages and merge consecutive thinking/tool_execution
            const rawMsgs = (data.messages || []).map(m => ({
                role: m.role,
                content: m.content,
                timestamp: m.timestamp,
                type: m.type || 'message',
                tool_calls: m.tool_calls || [],
            }));
            state.messages = mergeConsecutiveMessages(rawMsgs);
            state.turnCount = state.messages.filter(m => m.role === 'assistant').length;
            renderMessages();
            showToast(`Loaded: ${data.title}`);
            // Close drawer
            document.getElementById('threadsDrawer').classList.remove('visible');
            state.threadsVisible = false;
            break;
            
        case 'thread_saved':
            showToast('Conversation saved');
            break;
    }
}

// Send message
async function sendMessage() {
    const message = elements.messageInput.value.trim();
    if (!message || state.isThinking) return;
    
    // Add user message to UI
    addUserMessage(message);
    
    // Clear input
    elements.messageInput.value = '';
    autoResizeTextarea();
    
    // Send via WebSocket or REST
    if (state.connected && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify({
            type: 'chat',
            message: message,
            model: state.tiles.chat.model,
        }));
    } else {
        // Fallback to REST API
        setThinking(true);
        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message, model: state.tiles.chat.model }),
            });
            const data = await response.json();
            
            if (response.ok) {
                addAssistantMessage(data.response, []);
            } else {
                addErrorMessage(data.detail || 'Error sending message');
            }
        } catch (error) {
            addErrorMessage(error.message);
        } finally {
            setThinking(false);
        }
    }
}

// Message rendering
function addUserMessage(content) {
    state.messages.push({
        role: 'user',
        content: content,
        timestamp: new Date().toISOString(),
    });
    state.threadHasMessages = true; // Mark thread as having messages
    renderMessages();
    scrollToBottom();
}

function addThinkingMessage(content, toolCalls = [], explicitType = null) {
    // Determine message type based on content or explicit type
    // - "thinking" = has meaningful text content (LLM reasoning)
    // - "tool_execution" = just tool calls, no real content
    const hasContent = content && content.trim() && content.trim().length > 0;
    const hasToolCalls = toolCalls && toolCalls.length > 0;
    
    // Skip if nothing to show
    if (!hasContent && !hasToolCalls) {
        return;
    }
    
    // Use explicit type if provided, otherwise determine from content
    const msgType = explicitType || (hasContent ? 'thinking' : 'tool_execution');
    
    // Check if we can merge with the previous message of the same type
    const lastMsg = state.messages[state.messages.length - 1];
    if (lastMsg && lastMsg.type === msgType && lastMsg.role === 'assistant') {
        // Merge: append content and tool calls to existing message
        if (hasContent) {
            lastMsg.content = lastMsg.content 
                ? lastMsg.content + '\n\n' + content 
                : content;
        }
        if (hasToolCalls) {
            lastMsg.tool_calls = [...(lastMsg.tool_calls || []), ...toolCalls];
        }
        renderMessages();
        scrollToBottom();
        return;
    }
    
    // Create new message
    state.messages.push({
        role: 'assistant',
        content: content || '',
        tool_calls: toolCalls,
        type: msgType,
        timestamp: new Date().toISOString(),
    });
    renderMessages();
    scrollToBottom();
}

function addAssistantMessage(content, toolCalls = []) {
    // Skip empty messages (tool-call-only intermediate responses)
    if (!content || content.trim() === '') {
        return;
    }
    state.messages.push({
        role: 'assistant',
        content: content,
        tool_calls: toolCalls,
        type: 'response',
        timestamp: new Date().toISOString(),
    });
    renderMessages();
    scrollToBottom();
}

// Streaming message functions
function handleStreamToken(token) {
    if (!state.isStreaming) {
        // First token - start streaming
        state.isStreaming = true;
        state.streamingContent = '';
        // Hide thinking indicator when streaming starts
        setThinking(false);
        // Add a placeholder streaming message
        state.messages.push({
            role: 'assistant',
            content: '',
            tool_calls: [],
            type: 'streaming',
            timestamp: new Date().toISOString(),
        });
        // Render once to create the element
        renderMessages();
    }
    
    // Accumulate content
    state.streamingContent += token;
    
    // Update the streaming message content in state
    const streamingMsg = state.messages[state.messages.length - 1];
    if (streamingMsg && streamingMsg.type === 'streaming') {
        streamingMsg.content = state.streamingContent;
        
        // Update DOM directly instead of full re-render (performance optimization)
        const allMessages = document.querySelectorAll('.message');
        const lastMessage = allMessages[allMessages.length - 1];
        if (lastMessage && lastMessage.classList.contains('streaming')) {
            const contentEl = lastMessage.querySelector('.message-content');
            if (contentEl) {
                const contentHtml = marked.parse(state.streamingContent);
                contentEl.innerHTML = contentHtml + '<span class="streaming-cursor">▌</span>';
            }
        }
        scrollToBottom();
    }
}

function handleStreamEnd() {
    if (state.isStreaming) {
        // Finalize the streaming message
        const streamingMsg = state.messages[state.messages.length - 1];
        if (streamingMsg && streamingMsg.type === 'streaming') {
            streamingMsg.type = 'response';
        }
        state.isStreaming = false;
        state.streamingContent = '';
        // Full render to remove streaming class and cursor
        renderMessages();
    }
}

function handleStreamCancel() {
    // Cancel streaming - remove the streaming message, content will appear as thinking message
    if (state.isStreaming) {
        // Remove the streaming message placeholder
        const lastMsg = state.messages[state.messages.length - 1];
        if (lastMsg && lastMsg.type === 'streaming') {
            state.messages.pop();
        }
        state.isStreaming = false;
        state.streamingContent = '';
        renderMessages();
    }
}

function addErrorMessage(error) {
    const friendlyError = mapErrorMessage(error);
    state.messages.push({
        role: 'error',
        content: friendlyError,
        timestamp: new Date().toISOString(),
    });
    renderMessages();
    scrollToBottom();
}

// Map technical errors to user-friendly messages
function mapErrorMessage(error) {
    const errorStr = String(error);
    
    // Check for known error patterns
    for (const [pattern, friendly] of Object.entries(ERROR_MESSAGES)) {
        if (errorStr.toLowerCase().includes(pattern.toLowerCase())) {
            return friendly;
        }
    }
    
    // API key errors
    if (errorStr.includes('ANTHROPIC_API_KEY') || errorStr.includes('OPENAI_API_KEY') || errorStr.includes('GOOGLE_API_KEY')) {
        return 'API key not configured for this model. Please check your environment variables.';
    }
    
    // Connection errors
    if (errorStr.includes('ECONNREFUSED') || errorStr.includes('ENOTFOUND')) {
        return 'Unable to connect to the server. Please check if all services are running.';
    }
    
    // Generic fallback
    return `Something went wrong: ${errorStr}`;
}

function renderMessages() {
    // Remove welcome message if there are messages
    const welcomeEl = elements.chatMessages.querySelector('.welcome-message');
    if (state.messages.length > 0 && welcomeEl) {
        welcomeEl.remove();
    }
    
    // Clear existing messages (except welcome)
    const existingMessages = elements.chatMessages.querySelectorAll('.message');
    existingMessages.forEach(el => el.remove());
    
    // Render messages, tracking rendered index for click handlers
    let renderedIndex = 0;
    state.messages.forEach((msg) => {
        // Skip completely empty messages (but keep thinking messages that have tool calls)
        const hasContent = msg.content && msg.content.trim();
        const hasToolCalls = msg.tool_calls && msg.tool_calls.length > 0;
        
        if (msg.role === 'assistant' && !hasContent && msg.type !== 'thinking' && msg.type !== 'tool_execution') {
            return;
        }
        // Skip thinking/tool_execution messages with no content and no tools
        if ((msg.type === 'thinking' || msg.type === 'tool_execution') && !hasContent && !hasToolCalls) {
            return;
        }
        
        const messageEl = createMessageElement(msg, renderedIndex);
        elements.chatMessages.appendChild(messageEl);
        renderedIndex++;
    });
}

function createMessageElement(msg, index) {
    const div = document.createElement('div');
    
    // Handle thinking messages (LLM reasoning with actual content)
    if (msg.type === 'thinking') {
        div.className = 'message assistant thinking';
        const hasToolCalls = msg.tool_calls && msg.tool_calls.length > 0;
        const toolsList = hasToolCalls 
            ? (msg.tool_calls || []).map(t => `<span class="thinking-tool">${escapeHtml(t)}</span>`).join('')
            : '';
        
        div.innerHTML = `
            <div class="message-avatar thinking-avatar">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
            </div>
            <div class="thinking-bubble" onclick="toggleThinkingMessage(${index})">
                <div class="thinking-header">
                    <span class="thinking-label">Thinking</span>
                    ${hasToolCalls ? `<span class="thinking-tools">${toolsList}</span>` : ''}
                    <i data-lucide="chevron-down" class="thinking-chevron"></i>
                </div>
                <div class="thinking-content">${marked.parse(msg.content)}</div>
            </div>
        `;
        lucide.createIcons({nodes: [div]});
        return div;
    }
    
    // Handle tool execution messages (just showing which tools are running)
    if (msg.type === 'tool_execution') {
        div.className = 'message assistant tool-execution';
        const toolsList = (msg.tool_calls || []).map(t => `<span class="tool-badge">${escapeHtml(t)}</span>`).join('');
        
        div.innerHTML = `
            <div class="tool-execution-bubble">
                <svg class="tool-icon" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>
                <div class="tool-list">${toolsList}</div>
            </div>
        `;
        return div;
    }
    
    div.className = `message ${msg.role}`;
    
    if (msg.role === 'error') {
        div.innerHTML = `
            <div class="message-avatar">⚠️</div>
            <div class="message-content" style="background: var(--error); color: white;">
                <p>${escapeHtml(msg.content)}</p>
            </div>
        `;
        return div;
    }
    
    // Handle streaming messages (show cursor)
    const isStreaming = msg.type === 'streaming';
    
    const contentHtml = marked.parse(msg.content || '');
    
    // Add streaming class for cursor animation
    if (isStreaming) {
        div.className = 'message assistant streaming';
    } else {
        div.className = `message ${msg.role}`;
    }
    
    // User messages get avatar, assistant messages don't (ChatGPT style)
    if (msg.role === 'user') {
        div.innerHTML = `
            <div class="message-avatar"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg></div>
            <div class="message-content">
                ${contentHtml}
            </div>
        `;
    } else {
        div.innerHTML = `
            <div class="message-content">
                ${contentHtml}${isStreaming ? '<span class="streaming-cursor">▌</span>' : ''}
            </div>
        `;
    }
    
    return div;
}

// Toggle thinking message expansion
function toggleThinkingMessage(index) {
    // Find message by counting rendered messages
    const allMessages = document.querySelectorAll('.message');
    if (allMessages[index]) {
        allMessages[index].classList.toggle('expanded');
        lucide.createIcons({nodes: [allMessages[index]]});
    }
}

function scrollToBottom() {
    elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
}

function setThinking(thinking) {
    state.isThinking = thinking;
    elements.thinkingIndicator.classList.toggle('visible', thinking);
    elements.sendBtn.disabled = thinking;
}

// Clear chat - deletes current thread and creates a new one
async function clearChat() {
    if (!confirm('Delete this conversation and start a new one?')) return;
    
    try {
        // Delete the current thread
        if (state.currentThreadId) {
            await fetch(`/api/threads/${state.currentThreadId}`, { method: 'DELETE' });
        }
        
        // Create a new thread
        await createNewThread();
        
        showToast('Conversation deleted');
    } catch (error) {
        console.error('Failed to clear chat:', error);
        showToast('Failed to delete conversation', true);
    }
}

// Load tools with retry
async function loadTools() {
    const maxRetries = 3;
    let lastError = null;
    
    for (let i = 0; i < maxRetries; i++) {
        try {
            const response = await fetch('/api/tools');
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();
            if (data.servers && data.servers.length > 0) {
                renderTools(data.servers);
                return;
            } else if (i < maxRetries - 1) {
                // Wait before retry if no servers yet
                await new Promise(r => setTimeout(r, 1000));
            }
        } catch (error) {
            lastError = error;
            if (i < maxRetries - 1) {
                await new Promise(r => setTimeout(r, 1000));
            }
        }
    }
    
    elements.toolsList.innerHTML = `<div class="empty-state">Waiting for MCP servers...</div>`;
}

function renderTools(servers) {
    if (!servers || servers.length === 0) {
        elements.toolsList.innerHTML = `<div class="empty-state">No servers connected</div>`;
        return;
    }
    
    // Store tools data for detail lookup
    window.mcpToolsData = servers;
    const totalTools = servers.reduce((sum, s) => sum + s.tools.length, 0);
    const totalResources = servers.reduce((sum, s) => sum + (s.resources?.length || 0), 0);
    
    const summaryParts = [`${servers.length} servers`, `${totalTools} tools`];
    if (totalResources > 0) summaryParts.push(`${totalResources} resources`);
    
    elements.toolsList.innerHTML = `
        <div class="mcp-summary">${summaryParts.join(' · ')}</div>
        ${servers.map(server => `
            <div class="mcp-server-item" onclick="toggleMcpServer(this)">
                <div class="server-header-row">
                    <span class="server-name">${escapeHtml(server.name)}</span>
                    <span class="server-badge">${server.tools.length}${server.resources?.length ? ` / ${server.resources.length}` : ''}</span>
                </div>
                <div class="mcp-server-content">
                    ${server.tools.length > 0 ? `
                        <div class="mcp-subsection">
                            <div class="mcp-subsection-header">Tools</div>
                            <div class="mcp-tools-list visible">
                                ${server.tools.map(tool => `
                                    <div class="mcp-tool-item" 
                                         onclick="event.stopPropagation(); showToolDetail('${escapeHtml(server.name)}', '${escapeHtml(tool.name)}')"
                                         title="Click for details">${escapeHtml(tool.name)}</div>
                                `).join('')}
                            </div>
                        </div>
                    ` : ''}
                    ${server.resources?.length > 0 ? `
                        <div class="mcp-subsection">
                            <div class="mcp-subsection-header">Resources</div>
                            <div class="mcp-resources-list">
                                ${server.resources.map(resource => `
                                    <div class="mcp-resource-item" 
                                         onclick="event.stopPropagation(); showResourceDetail('${escapeHtml(server.name)}', '${escapeHtml(resource.uri)}')"
                                         title="${escapeHtml(resource.description || resource.uri)}">
                                        <span class="resource-name">${escapeHtml(resource.name || resource.uri)}</span>
                                        ${resource.mimeType ? `<span class="resource-type">${escapeHtml(resource.mimeType)}</span>` : ''}
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                    ` : ''}
                </div>
            </div>
        `).join('')}
    `;
    
    lucide.createIcons();
}

function toggleMcpServer(item) {
    item.classList.toggle('expanded');
}

// Show resource detail in a modal
function showResourceDetail(serverName, resourceUri) {
    const server = window.mcpToolsData?.find(s => s.name === serverName);
    const resource = server?.resources?.find(r => r.uri === resourceUri);
    
    if (!resource) {
        console.error('Resource not found:', serverName, resourceUri);
        return;
    }
    
    // Reuse tool detail modal
    let modal = document.getElementById('toolDetailModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'toolDetailModal';
        modal.className = 'tool-detail-modal';
        modal.innerHTML = `
            <div class="tool-detail-backdrop" onclick="closeToolDetail()"></div>
            <div class="tool-detail-content">
                <div class="tool-detail-header">
                    <h3 id="toolDetailTitle"></h3>
                    <button class="icon-btn" onclick="closeToolDetail()">
                        <i data-lucide="x"></i>
                    </button>
                </div>
                <div class="tool-detail-body" id="toolDetailBody"></div>
            </div>
        `;
        document.body.appendChild(modal);
    }
    
    document.getElementById('toolDetailTitle').textContent = resource.name || 'Resource';
    document.getElementById('toolDetailBody').innerHTML = `
        <div class="tool-detail-section">
            <h4>Server</h4>
            <p class="tool-server-badge">${escapeHtml(serverName)}</p>
        </div>
        <div class="tool-detail-section">
            <h4>URI</h4>
            <p class="resource-uri">${escapeHtml(resource.uri)}</p>
        </div>
        ${resource.mimeType ? `
            <div class="tool-detail-section">
                <h4>MIME Type</h4>
                <p>${escapeHtml(resource.mimeType)}</p>
            </div>
        ` : ''}
        <div class="tool-detail-section">
            <h4>Description</h4>
            <p class="tool-description">${escapeHtml(resource.description || 'No description available')}</p>
        </div>
    `;
    
    modal.classList.add('visible');
    lucide.createIcons();
}

// Show tool detail in a modal/popup
async function showToolDetail(serverName, toolName) {
    // Create modal if it doesn't exist
    let modal = document.getElementById('toolDetailModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'toolDetailModal';
        modal.className = 'tool-detail-modal';
        modal.innerHTML = `
            <div class="tool-detail-backdrop" onclick="closeToolDetail()"></div>
            <div class="tool-detail-content">
                <div class="tool-detail-header">
                    <h3 id="toolDetailTitle"></h3>
                    <button class="icon-btn" onclick="closeToolDetail()">
                        <i data-lucide="x"></i>
                    </button>
                </div>
                <div class="tool-detail-body" id="toolDetailBody"></div>
            </div>
        `;
        document.body.appendChild(modal);
    }
    
    // Show modal with loading state
    document.getElementById('toolDetailTitle').textContent = toolName;
    document.getElementById('toolDetailBody').innerHTML = `
        <div class="loading-state">
            <div class="thinking-dots"><span></span><span></span><span></span></div>
            <p>Loading tool details...</p>
        </div>
    `;
    modal.classList.add('visible');
    lucide.createIcons();
    
    // Fetch full tool details from API
    try {
        const response = await fetch(`/api/tool/${encodeURIComponent(serverName)}/${encodeURIComponent(toolName)}`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const tool = await response.json();
        
        // Build parameters HTML
        let paramsHtml = '<p class="empty-hint">No parameters</p>';
        if (tool.inputSchema && tool.inputSchema.properties) {
            const props = tool.inputSchema.properties;
            const required = tool.inputSchema.required || [];
            
            paramsHtml = `<div class="tool-params">
                ${Object.entries(props).map(([name, schema]) => `
                    <div class="tool-param">
                        <div class="tool-param-header">
                            <code class="tool-param-name">${escapeHtml(name)}</code>
                            <span class="tool-param-type">${escapeHtml(schema.type || 'any')}</span>
                            ${required.includes(name) ? '<span class="tool-param-required">required</span>' : ''}
                        </div>
                        ${schema.description ? `<div class="tool-param-desc">${escapeHtml(schema.description)}</div>` : ''}
                    </div>
                `).join('')}
            </div>`;
        }
        
        document.getElementById('toolDetailBody').innerHTML = `
            <div class="tool-detail-section">
                <h4>Server</h4>
                <p class="tool-server-badge">${escapeHtml(serverName)}</p>
            </div>
            <div class="tool-detail-section">
                <h4>Description</h4>
                <p class="tool-description">${escapeHtml(tool.description || 'No description available')}</p>
            </div>
            <div class="tool-detail-section">
                <h4>Parameters</h4>
                ${paramsHtml}
            </div>
        `;
    } catch (error) {
        console.error('Failed to load tool details:', error);
        document.getElementById('toolDetailBody').innerHTML = `
            <div class="error-state">
                <p>Failed to load tool details</p>
                <p class="error-hint">${escapeHtml(error.message)}</p>
            </div>
        `;
    }
}

function closeToolDetail() {
    const modal = document.getElementById('toolDetailModal');
    if (modal) {
        modal.classList.remove('visible');
    }
}

// === Chat Model Tile ===

function renderChatModelSelector() {
    const dropdown = document.getElementById('chatModelDropdown');
    if (!dropdown) return;
    
    const modelNames = Object.keys(MODELS);
    
    if (modelNames.length === 0) {
        dropdown.innerHTML = '<div class="model-option">Loading models...</div>';
        return;
    }
    
    // Find current model name
    let currentName = null;
    for (const [name, config] of Object.entries(MODELS)) {
        if (`${config.provider}/${config.model}` === state.tiles.chat.model) {
            currentName = name;
            break;
        }
    }
    
    // Default to first model if not found
    if (!currentName) {
        currentName = modelNames[0];
        const firstConfig = MODELS[currentName];
        state.tiles.chat.model = `${firstConfig.provider}/${firstConfig.model}`;
        
        // Sync with backend
        fetch('/api/model', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider: firstConfig.provider, model: firstConfig.model })
        }).catch(err => console.error('Failed to sync model with backend:', err));
    }
    
    const pricing = TOKEN_PRICING;
    dropdown.innerHTML = modelNames.map(name => {
        const config = MODELS[name];
        const fullModel = `${config.provider}/${config.model}`;
        const isSelected = fullModel === state.tiles.chat.model;
        const p = pricing[config.model] || { input: 0, output: 0 };
        const pricingText = `$${p.input}/$${p.output}/M`;
        return `
            <div class="model-option ${isSelected ? 'selected' : ''}" 
                 data-name="${name}"
                 onclick="selectChatModel('${name}')">
                <span class="model-name">${escapeHtml(name)}</span>
                <span class="model-pricing">${pricingText}</span>
            </div>
        `;
    }).join('');
    
    document.getElementById('currentChatModel').textContent = currentName;
}

async function selectChatModel(name) {
    const config = MODELS[name];
    if (!config) return;
    
    const fullModel = `${config.provider}/${config.model}`;
    state.tiles.chat.model = fullModel;
    
    document.getElementById('currentChatModel').textContent = name;
    document.getElementById('chatModelDropdown').classList.remove('visible');
    
    // Update selection in dropdown
    document.querySelectorAll('#chatModelDropdown .model-option').forEach(opt => {
        opt.classList.toggle('selected', opt.dataset.name === name);
    });
    
    // Notify backend (model can change anytime now)
    try {
        const response = await fetch('/api/model', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider: config.provider, model: config.model }),
        });
        
        if (response.ok) {
            showToast(`Chat model changed to ${name}`);
        } else {
            const data = await response.json();
            showToast(data.detail || 'Failed to change model', true);
        }
    } catch (error) {
        console.error('Failed to set model:', error);
        showToast('Failed to change model', true);
    }
    
    // Refresh usage display (recalculate cost with new model pricing)
    loadChatUsage();
}

function updateCurrentChatModelDisplay(name) {
    const display = document.getElementById('currentChatModel');
    if (display) {
        display.textContent = name;
    }
}

// === Distillation Model Tile ===

let DISTILLATION_MODELS = {};
let DISTILL_PRICING = {};

async function fetchDistillationModels() {
    try {
        const response = await fetch('/api/distillation/models');
        const data = await response.json();
        
        DISTILLATION_MODELS = {};
        DISTILL_PRICING = {};
        
        for (const m of data.models) {
            DISTILLATION_MODELS[m.name] = { id: m.id };
            DISTILL_PRICING[m.id] = m.pricing || { input: 0, output: 0 };
        }
        
        if (data.current) {
            state.tiles.distill.model = data.current.model;
        }
        
        console.log('Distillation models loaded:', Object.keys(DISTILLATION_MODELS));
    } catch (error) {
        console.error('Failed to fetch distillation models:', error);
        DISTILLATION_MODELS = {
            'GPT-5 Nano': { id: 'gpt-5-nano' },
            'GPT-4o Mini': { id: 'gpt-4o-mini' },
            'Local Rules': { id: 'local-rules' }
        };
    }
}

function renderDistillModelSelector() {
    const dropdown = document.getElementById('distillModelDropdown');
    if (!dropdown) return;
    
    const modelNames = Object.keys(DISTILLATION_MODELS);
    
    if (modelNames.length === 0) {
        dropdown.innerHTML = '<div class="model-option">Loading...</div>';
        return;
    }
    
    // Find current model name
    let currentName = null;
    for (const [name, config] of Object.entries(DISTILLATION_MODELS)) {
        if (config.id === state.tiles.distill.model) {
            currentName = name;
            break;
        }
    }
    currentName = currentName || modelNames[0];
    
    dropdown.innerHTML = modelNames.map(name => {
        const config = DISTILLATION_MODELS[name];
        const isSelected = config.id === state.tiles.distill.model;
        const pricing = DISTILL_PRICING[config.id] || { input: 0, output: 0 };
        const pricingText = config.id === 'local-rules' ? 'Free' : `$${pricing.input}/$${pricing.output}/M`;
        return `
            <div class="model-option ${isSelected ? 'selected' : ''}" 
                 data-id="${config.id}"
                 onclick="selectDistillModel('${config.id}')">
                <span class="model-name">${escapeHtml(name)}</span>
                <span class="model-pricing">${pricingText}</span>
            </div>
        `;
    }).join('');
    
    document.getElementById('currentDistillModel').textContent = currentName;
}

async function selectDistillModel(modelId) {
    // Find model name from id
    let modelName = null;
    for (const [name, config] of Object.entries(DISTILLATION_MODELS)) {
        if (config.id === modelId) {
            modelName = name;
            break;
        }
    }
    if (!modelName) return;
    
    state.tiles.distill.model = modelId;
    document.getElementById('currentDistillModel').textContent = modelName;
    document.getElementById('distillModelDropdown').classList.remove('visible');
    
    // Update selection in dropdown
    document.querySelectorAll('#distillModelDropdown .model-option').forEach(opt => {
        opt.classList.toggle('selected', opt.dataset.id === modelId);
    });
    
    // Notify backend
    try {
        const response = await fetch('/api/distillation/model', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ model: modelId }),
        });
        
        if (response.ok) {
            showToast(`Distillation model changed to ${modelName}`);
        } else {
            const data = await response.json();
            showToast(data.detail || 'Failed to change distillation model', true);
        }
    } catch (error) {
        console.error('Failed to set distillation model:', error);
        showToast('Failed to change distillation model', true);
    }
    
    // Refresh usage display
    updateDistillUsageDisplay();
}

// === Tile Filter Management ===

async function setTileFilter(tile, filter) {
    state.tiles[tile].filter = filter;
    
    // Update active button
    const filterContainer = document.querySelector(`.tile-filters[data-tile="${tile}"]`);
    if (filterContainer) {
        filterContainer.querySelectorAll('.filter-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.filter === filter);
        });
    }
    
    // Fetch and refresh usage display for this tile
    if (tile === 'chat') {
        await loadChatUsage();
    } else if (tile === 'distill') {
        // Distillation doesn't have date filtering yet - just refresh
        updateDistillUsageDisplay();
    }
}

// === Chat Usage Display ===

async function loadChatUsage() {
    const filter = state.tiles.chat.filter;
    const container = document.getElementById('chatUsage');
    if (!container) return;
    
    try {
        let url = `/api/usage?filter=${filter}`;
        if (filter === 'thread' && state.currentThreadId) {
            url += `&thread_id=${state.currentThreadId}`;
        }
        
        // Always filter by currently selected model
        if (state.tiles.chat.model) {
            // Extract model name from "provider/model" format
            const modelName = state.tiles.chat.model.split('/').pop();
            if (modelName) {
                url += `&model=${encodeURIComponent(modelName)}`;
            }
        }
        
        const response = await fetch(url);
        const data = await response.json();
        
        // Backend calculates cost - we just display it
        state.tiles.chat.usage = {
            input_tokens: data.input_tokens || 0,
            output_tokens: data.output_tokens || 0,
            cost: data.cost || 0,
            calls: data.calls || 0,
            model: data.model || null,
            by_model: data.by_model || null,
        };
        
        updateChatUsageDisplay();
    } catch (error) {
        console.error('Failed to load chat usage:', error);
        container.innerHTML = '<div class="empty-state">Failed to load</div>';
    }
}

function updateChatUsageDisplay() {
    const container = document.getElementById('chatUsage');
    if (!container) return;
    
    const usage = state.tiles.chat.usage;
    
    if (!usage || (usage.calls === 0 && usage.input_tokens === 0)) {
        container.innerHTML = '<div class="empty-state">No API calls yet</div>';
        return;
    }
    
    const costStr = usage.cost < 0.01 ? `$${usage.cost.toFixed(4)}` : `$${usage.cost.toFixed(2)}`;
    
    container.innerHTML = `
        <div class="usage-row">
            <span class="label">Calls</span>
            <span class="value">${usage.calls}</span>
        </div>
        <div class="usage-row">
            <span class="label">Input</span>
            <span class="value">${usage.input_tokens.toLocaleString()}</span>
        </div>
        <div class="usage-row">
            <span class="label">Output</span>
            <span class="value">${usage.output_tokens.toLocaleString()}</span>
        </div>
        <div class="usage-row total">
            <span class="label">Cost</span>
            <span class="value">${costStr}</span>
        </div>
    `;
}

// === Distill Usage Display ===

async function loadDistillUsage() {
    try {
        // Filter by selected distillation model
        const model = state.tiles.distill.model || '';
        const params = new URLSearchParams();
        if (model) params.append('model', model);
        
        const url = '/api/distillation/usage' + (params.toString() ? '?' + params.toString() : '');
        const response = await fetch(url);
        const data = await response.json();
        state.tiles.distill.usage = data;
        updateDistillUsageDisplay();
    } catch (error) {
        console.error('Failed to load distillation usage:', error);
    }
}

function updateDistillUsageDisplay() {
    const container = document.getElementById('distillUsage');
    if (!container) return;
    
    const usage = state.tiles.distill.usage || { input_tokens: 0, output_tokens: 0, cost: 0, calls: 0 };
    
    if (!usage || usage.calls === 0) {
        container.innerHTML = '<div class="empty-state">No distillation yet</div>';
        return;
    }
    
    const costStr = usage.cost < 0.01 ? `$${usage.cost.toFixed(4)}` : `$${usage.cost.toFixed(2)}`;
    
    container.innerHTML = `
        <div class="usage-row">
            <span class="label">Calls</span>
            <span class="value">${usage.calls}</span>
        </div>
        <div class="usage-row">
            <span class="label">Input</span>
            <span class="value">${usage.input_tokens.toLocaleString()}</span>
        </div>
        <div class="usage-row">
            <span class="label">Output</span>
            <span class="value">${usage.output_tokens.toLocaleString()}</span>
        </div>
        <div class="usage-row total">
            <span class="label">Cost</span>
            <span class="value">${costStr}</span>
        </div>
    `;
}

// === Section Toggle ===

function toggleSection(sectionId) {
    const section = document.getElementById(sectionId);
    if (section) {
        section.classList.toggle('expanded');
    }
}

// Debug panel
async function loadDebugInfo() {
    try {
        const response = await fetch('/api/debug');
        const data = await response.json();
        updateFullDebugInfo(data);
    } catch (error) {
        console.error('Failed to load debug info:', error);
    }
}

function updateFullDebugInfo(data) {
    // Tool usage from server
    if (data.tool_usage) {
        state.toolUsage = data.tool_usage;
    }
    
    // Refresh chat and distillation usage displays
    updateChatUsageDisplay();
    loadDistillUsage();
}

function updateDebugDisplay() {
    const turnsEl = document.getElementById('debugTurns');
    if (turnsEl) turnsEl.textContent = state.turnCount;
    updateChatUsageDisplay();
    updateDistillUsageDisplay();
}

// Get filter cutoff timestamp (using calendar days in local timezone)
function getFilterCutoff(filter) {
    const now = new Date();
    
    switch (filter) {
        case 'thread': 
            return state.sessionStartTime; // Thread start time
        case 'day': {
            // Start of today (midnight local time)
            const startOfDay = new Date(now.getFullYear(), now.getMonth(), now.getDate());
            return startOfDay.getTime();
        }
        case 'week': {
            // Start of 7 days ago (midnight local time)
            const startOfWeek = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 7);
            return startOfWeek.getTime();
        }
        case 'month': {
            // Start of 30 days ago (midnight local time)
            const startOfMonth = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 30);
            return startOfMonth.getTime();
        }
        case 'all': 
            return 0;
        default: 
            return state.sessionStartTime;
    }
}

async function loadToolUsage() {
    // Load tool usage from backend for current thread
    const container = document.getElementById('toolUsageList');
    if (!container) return;
    
    if (!state.currentThreadId) {
        container.innerHTML = '<div class="empty-state">No tools called yet</div>';
        return;
    }
    
    try {
        const response = await fetch(`/api/tool-usage?thread_id=${state.currentThreadId}`);
        const data = await response.json();
        
        if (!data.tools || Object.keys(data.tools).length === 0) {
            container.innerHTML = '<div class="empty-state">No tools called yet</div>';
            return;
        }
        
        // Sort by count descending
        const entries = Object.entries(data.tools).sort((a, b) => b[1] - a[1]);
        
        container.innerHTML = entries.map(([name, count]) => `
            <div class="tool-usage-item">
                <span class="tool-name">${escapeHtml(name)}</span>
                <span class="tool-count">${count}</span>
            </div>
        `).join('');
    } catch (error) {
        console.error('Failed to load tool usage:', error);
        container.innerHTML = '<div class="empty-state">Failed to load</div>';
    }
}

function updateToolUsageDisplay() {
    // Now just calls the async backend loader
    loadToolUsage();
}

function trackTokenUsage(usage) {
    // Backend provides pre-calculated cost
    const inputTokens = usage.input_tokens || 0;
    const outputTokens = usage.output_tokens || 0;
    const cost = usage.cost || 0;
    
    // Update tile usage (only for thread filter - other filters aggregate from backend)
    if (state.tiles.chat.filter === 'thread') {
        state.tiles.chat.usage.input_tokens += inputTokens;
        state.tiles.chat.usage.output_tokens += outputTokens;
        state.tiles.chat.usage.cost += cost;
        state.tiles.chat.usage.calls += 1;
        updateChatUsageDisplay();
    }
    // For other filters, the aggregates need full backend refresh
    // (which happens on filter change anyway)
}

// Load usage data (tool usage and chat usage come from backend)
function loadUsageData() {
    // All usage data is now fetched from backend
    // This function is kept for initialization but does nothing
}

function formatModelName(model) {
    // Make model names more readable
    if (model.includes('claude')) return 'Claude';
    if (model.includes('gpt')) return 'ChatGPT';
    if (model.includes('gemini')) return 'Gemini';
    return model;
}

function formatNumber(num) {
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
    return num.toString();
}

// Utility
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Resizable panes
function initializeResizers() {
    // Create resize handles
    const leftSidebar = document.getElementById('leftSidebar');
    
    // Left sidebar resizer
    const leftResizer = document.createElement('div');
    leftResizer.className = 'resize-handle resize-handle-left';
    leftSidebar.appendChild(leftResizer);
    
    // Setup drag handlers - allow up to 50% of viewport
    setupResizer(leftResizer, leftSidebar, 'width', 280, window.innerWidth * 0.5);
}

function setupResizer(resizer, target, dimension, min, max) {
    let startPos, startSize;
    
    const onMouseMove = (e) => {
        const delta = e.clientX - startPos;
        let newSize = startSize + delta;
        newSize = Math.max(min, Math.min(max, newSize));
        target.style[dimension] = newSize + 'px';
        target.style.flex = 'none';
    };
    
    const onMouseUp = () => {
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
    };
    
    resizer.addEventListener('mousedown', (e) => {
        e.preventDefault();
        startPos = e.clientX;
        startSize = target.getBoundingClientRect().width;
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
    });
}

// Make functions available globally for onclick handlers
function toggleServerTools(serverName) {
    // Toggle server tools visibility in sidebar (placeholder if not implemented)
    console.log('toggleServerTools:', serverName);
}
window.toggleServerTools = toggleServerTools;
window.selectModel = selectChatModel;
window.toggleTheme = toggleTheme;
window.showToolDetail = showToolDetail;
window.showResourceDetail = showResourceDetail;
window.closeToolDetail = closeToolDetail;
window.toggleMcpServer = toggleMcpServer;
window.setTileFilter = setTileFilter;
window.toggleSection = toggleSection;
window.loadThread = loadThread;
window.deleteThread = deleteThread;
window.toggleLogDetails = toggleLogDetails;
window.toggleTurnGroup = toggleTurnGroup;
window.toggleLogsSection = toggleLogsSection;
window.toggleThinkingMessage = toggleThinkingMessage;
window.toggleUsageSection = toggleUsageSection;

// ========================================
// Thread Management Functions
// ========================================

function toggleThreadsDrawer() {
    const drawer = document.getElementById('threadsDrawer');
    state.threadsVisible = !state.threadsVisible;
    drawer.classList.toggle('visible', state.threadsVisible);
    
    if (state.threadsVisible) {
        loadThreads();
    }
}

async function loadThreads() {
    try {
        // Use WebSocket if available
        if (state.connected && state.ws.readyState === WebSocket.OPEN) {
            state.ws.send(JSON.stringify({ type: 'get_threads' }));
        } else {
            // Fallback to REST API
            const response = await fetch('/api/threads');
            const data = await response.json();
            state.threads = data.threads || [];
            state.currentThreadId = data.current_thread_id;
            renderThreadsList();
        }
    } catch (error) {
        console.error('Failed to load threads:', error);
    }
}

function renderThreadsList() {
    const container = document.getElementById('threadsList');
    
    if (!state.threads || state.threads.length === 0) {
        container.innerHTML = `
            <div class="threads-empty">
                <i data-lucide="message-square"></i>
                <p>No saved conversations yet</p>
            </div>
        `;
        lucide.createIcons();
        return;
    }
    
    container.innerHTML = state.threads.map(thread => {
        const isActive = thread.thread_id === state.currentThreadId;
        // Handle both possible property names from backend
        const date = new Date(thread.last_updated || thread.updated_at);
        const dateStr = formatRelativeDate(date);
        const msgCount = thread.message_count || 0;
        const hasEmoji = thread.emoji && thread.emoji.trim();
        
        return `
            <div class="thread-item ${isActive ? 'active' : ''}" onclick="loadThread('${thread.thread_id}')">
                <div class="thread-item-icon ${hasEmoji ? 'has-emoji' : ''}">
                    ${hasEmoji ? thread.emoji : '<i data-lucide="message-square"></i>'}
                </div>
                <div class="thread-item-content">
                    <div class="thread-item-title">${escapeHtml(thread.title)}</div>
                    <div class="thread-item-meta">
                        <span>${dateStr}</span>
                        <span>• ${msgCount} messages</span>
                    </div>
                </div>
                <div class="thread-item-actions">
                    <button class="icon-btn" onclick="event.stopPropagation(); deleteThread('${thread.thread_id}')" title="Delete">
                        <i data-lucide="trash-2"></i>
                    </button>
                </div>
            </div>
        `;
    }).join('');
    
    lucide.createIcons();
}

function formatRelativeDate(date) {
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);
    
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

async function createNewThread() {
    try {
        const response = await fetch('/api/threads', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: 'New Conversation' })
        });
        const data = await response.json();
        state.currentThreadId = data.thread_id;
        state.threadHasMessages = false; // New thread has no messages yet
        updateThreadTitle(data.title || 'New Conversation');
        updateThreadEmoji(null);  // Reset emoji for new thread
        state.messages = [];
        state.turnCount = 0;
        
        // Update model from response (thread is created with current model)
        if (data.model_provider && data.model_name) {
            state.tiles.chat.model = `${data.model_provider}/${data.model_name}`;
        }
        
        // Reset usage for new thread
        state.tiles.chat.usage = { input_tokens: 0, output_tokens: 0, cost: 0, calls: 0 };
        
        // Refresh usage displays for the new thread
        updateChatUsageDisplay();
        updateToolUsageDisplay();
        loadDistillUsage();
        
        // Clear logs display for new thread
        const logsList = document.getElementById('llmLogsList');
        if (logsList) {
            logsList.innerHTML = '<div class="empty-state">No logs yet</div>';
        }
        
        renderMessages();
        showToast('New conversation started');
        
        // Focus the title input so user can name it
        const titleInput = document.getElementById('currentThreadTitle');
        titleInput.select();
        
        // Close drawer if open
        document.getElementById('threadsDrawer').classList.remove('visible');
        state.threadsVisible = false;
    } catch (error) {
        console.error('Failed to create thread:', error);
        showToast('Failed to create conversation', true);
    }
}

// Merge consecutive messages of the same type (for thinking/tool_execution)
function mergeConsecutiveMessages(messages) {
    if (!messages || messages.length === 0) return [];
    
    const merged = [];
    for (const msg of messages) {
        const last = merged[merged.length - 1];
        
        // Merge consecutive tool_execution messages
        if (last && 
            last.type === 'tool_execution' && 
            msg.type === 'tool_execution' &&
            last.role === msg.role) {
            // Append tool calls
            last.tool_calls = [...(last.tool_calls || []), ...(msg.tool_calls || [])];
            continue;
        }
        
        // Merge consecutive thinking messages
        if (last && 
            last.type === 'thinking' && 
            msg.type === 'thinking' &&
            last.role === msg.role) {
            // Append content and tool calls
            if (msg.content && msg.content.trim()) {
                last.content = last.content 
                    ? last.content + '\n\n' + msg.content 
                    : msg.content;
            }
            last.tool_calls = [...(last.tool_calls || []), ...(msg.tool_calls || [])];
            continue;
        }
        
        merged.push({...msg});
    }
    return merged;
}

async function loadThread(threadId) {
    try {
        const response = await fetch(`/api/threads/${threadId}/load`, { method: 'POST' });
        const data = await response.json();
        
        state.currentThreadId = data.thread_id;
        updateThreadTitle(data.title);
        updateThreadEmoji(data.emoji);
        
        // Map and merge consecutive thinking/tool_execution messages
        const rawMessages = (data.messages || []).map(m => ({
            role: m.role,
            content: m.content,
            timestamp: m.timestamp,
            type: m.type || 'message',
            tool_calls: m.tool_calls || [],
        }));
        state.messages = mergeConsecutiveMessages(rawMessages);
        state.threadHasMessages = state.messages.length > 0;
        state.turnCount = state.messages.filter(m => m.role === 'assistant' && m.type !== 'thinking').length;
        
        // Update model from thread's model (server already switched)
        if (data.model_provider && data.model_name) {
            state.tiles.chat.model = `${data.model_provider}/${data.model_name}`;
            
            // Find and update model display name
            for (const [name, config] of Object.entries(MODELS)) {
                if (config.model === data.model_name) {
                    updateCurrentChatModelDisplay(name);
                    break;
                }
            }
        }
        
        // Refresh usage displays (respects current filter setting)
        loadChatUsage();
        updateToolUsageDisplay();
        loadDistillUsage();
        
        // Refresh LLM logs for this thread
        loadLLMLogs();
        
        renderMessages();
        showToast(`Loaded: ${data.title}`);
        
        // Close drawer
        document.getElementById('threadsDrawer').classList.remove('visible');
        state.threadsVisible = false;
    } catch (error) {
        console.error('Failed to load thread:', error);
        showToast('Failed to load conversation', true);
    }
}

async function deleteThread(threadId) {
    if (!confirm('Delete this conversation?')) return;
    
    try {
        const response = await fetch(`/api/threads/${threadId}`, { method: 'DELETE' });
        if (response.ok) {
            // If we deleted the current thread, create a new one
            if (threadId === state.currentThreadId) {
                await createNewThread();
            }
            loadThreads();
            showToast('Conversation deleted');
        }
    } catch (error) {
        console.error('Failed to delete thread:', error);
        showToast('Failed to delete conversation', true);
    }
}

function filterThreads(query) {
    const normalizedQuery = query.toLowerCase().trim();
    const items = document.querySelectorAll('.thread-item');
    
    items.forEach(item => {
        const title = item.querySelector('.thread-item-title').textContent.toLowerCase();
        const matches = !normalizedQuery || title.includes(normalizedQuery);
        item.style.display = matches ? 'flex' : 'none';
    });
}

function updateThreadTitle(title) {
    state.currentThreadTitle = title;
    const titleEl = document.getElementById('currentThreadTitle');
    if (titleEl) {
        titleEl.value = title;
    }
}

function updateThreadEmoji(emoji) {
    state.currentThreadEmoji = emoji;
    const emojiBtn = document.getElementById('threadEmojiBtn');
    if (emojiBtn) {
        emojiBtn.textContent = emoji || '💬';
    }
}

// Emojis for thread icons organized by category
const THREAD_EMOJIS = {
    'Frequent': ['💬', '📝', '🏃', '🍽️', '💪', '🎯', '📊', '💡', '🔧', '✨', '🚀', '📅'],
    'Smileys': ['😀', '😊', '😄', '😁', '😅', '🤣', '😂', '🙂', '😉', '😍', '🥰', '😘', '😎', '🤔', '🤗', '🤩', '😴', '😌', '🥳', '😇', '🤓', '😏', '😤', '😢', '😭', '😱', '🤯', '🥺', '😬', '🙄'],
    'People': ['👋', '🤚', '✋', '🖐️', '👌', '🤌', '✌️', '🤞', '🤟', '🤘', '👍', '👎', '👏', '🙌', '👐', '🤝', '🙏', '💪', '🦾', '🦵', '👀', '👁️', '👄', '👅', '🧠', '👶', '👧', '👦', '👩', '👨', '👩‍🦰', '👨‍🦰', '👩‍🦱', '👨‍🦱', '👩‍🦳', '👨‍🦳', '👩‍🦲', '👨‍🦲', '🧔', '👵', '👴', '👷', '👮', '🕵️', '👨‍⚕️', '👩‍⚕️', '👨‍🍳', '👩‍🍳', '👨‍🎓', '👩‍🎓', '👨‍💻', '👩‍💻', '👨‍👩‍👧', '👨‍👩‍👦', '👥', '🧑‍🤝‍🧑'],
    'Animals': ['🐶', '🐱', '🐭', '🐹', '🐰', '🦊', '🐻', '🐼', '🐨', '🐯', '🦁', '🐮', '🐷', '🐸', '🐵', '🐔', '🐧', '🐦', '🐤', '🦆', '🦅', '🦉', '🦇', '🐺', '🐗', '🐴', '🦄', '🐝', '🐛', '🦋', '🐌', '🐞', '🐜', '🦟', '🦗', '🐢', '🐍', '🦎', '🦂', '🐙', '🦑', '🦐', '🦞', '🦀', '🐡', '🐠', '🐟', '🐬', '🐳', '🐋', '🦈', '🐊'],
    'Food': ['🍎', '🍊', '🍋', '🍌', '🍉', '🍇', '🍓', '🫐', '🍈', '🍒', '🍑', '🥭', '🍍', '🥥', '🥝', '🍅', '🥑', '🥦', '🥬', '🥒', '🌶️', '🫑', '🌽', '🥕', '🧄', '🧅', '🥔', '🍠', '🥐', '🥖', '🍞', '🥨', '🧀', '🥚', '🍳', '🧈', '🥞', '🧇', '🥓', '🥩', '🍗', '🍖', '🌭', '🍔', '🍟', '🍕', '🫓', '🥪', '🥙', '🧆', '🌮', '🌯', '🫔', '🥗', '🥘', '🍜', '🍝', '🍣', '🍱', '🥟', '🍤', '🍙', '🍚', '🍘', '🍥', '🥮', '🍢', '🍡', '🍧', '🍨', '🍦', '🥧', '🧁', '🍰', '🎂', '🍮', '🍭', '🍬', '🍫', '🍿', '🍩', '🍪', '☕', '🍵', '🧃', '🥤', '🧋', '🍶', '🍺', '🍻', '🥂', '🍷', '🥃', '🍸', '🍹', '🧊'],
    'Activities': ['⚽', '🏀', '🏈', '⚾', '🥎', '🎾', '🏐', '🏉', '🥏', '🎱', '🪀', '🏓', '🏸', '🏒', '🏑', '🥍', '🏏', '🪃', '🥅', '⛳', '🪁', '🏹', '🎣', '🤿', '🥊', '🥋', '🎽', '🛹', '🛼', '🛷', '⛸️', '🥌', '🎿', '⛷️', '🏂', '🪂', '🏋️', '🤼', '🤸', '⛹️', '🤾', '🏌️', '🏇', '🧘', '🏄', '🏊', '🤽', '🚣', '🧗', '🚴', '🚵', '🎖️', '🏆', '🥇', '🥈', '🥉', '🏅', '🎪', '🎭', '🎨', '🎬', '🎤', '🎧', '🎼', '🎹', '🥁', '🎷', '🎺', '🎸', '🪕', '🎻', '🎲', '🎯', '🎳', '🎮', '🎰', '🧩'],
    'Travel': ['🚗', '🚕', '🚙', '🚌', '🚎', '🏎️', '🚓', '🚑', '🚒', '🚐', '🛻', '🚚', '🚛', '🚜', '🏍️', '🛵', '🚲', '🛴', '🛺', '🚨', '🚔', '🚍', '🚘', '🚖', '🚡', '🚠', '🚟', '🚃', '🚋', '🚞', '🚝', '🚄', '🚅', '🚈', '🚂', '🚆', '🚇', '🚊', '🚉', '✈️', '🛫', '🛬', '🛩️', '💺', '🛰️', '🚀', '🛸', '🚁', '🛶', '⛵', '🚤', '🛥️', '🛳️', '⛴️', '🚢', '⚓', '🪝', '⛽', '🚧', '🚦', '🚥', '🗺️', '🗿', '🗽', '🗼', '🏰', '🏯', '🏟️', '🎡', '🎢', '🎠', '⛲', '⛱️', '🏖️', '🏝️', '🏜️', '🌋', '⛰️', '🏔️', '🗻', '🏕️', '⛺', '🏠', '🏡', '🏘️', '🏚️', '🏗️', '🏢', '🏭', '🏬', '🏣', '🏤', '🏥', '🏦', '🏨', '🏪', '🏫', '🏩', '💒', '🏛️', '⛪', '🕌', '🕍', '🛕', '🕋'],
    'Objects': ['⌚', '📱', '📲', '💻', '⌨️', '🖥️', '🖨️', '🖱️', '🖲️', '🕹️', '🗜️', '💽', '💾', '💿', '📀', '📼', '📷', '📸', '📹', '🎥', '📽️', '🎞️', '📞', '☎️', '📟', '📠', '📺', '📻', '🎙️', '🎚️', '🎛️', '🧭', '⏱️', '⏲️', '⏰', '🕰️', '⌛', '⏳', '📡', '🔋', '🔌', '💡', '🔦', '🕯️', '🪔', '🧯', '🛢️', '💸', '💵', '💴', '💶', '💷', '💰', '💳', '💎', '⚖️', '🪜', '🧰', '🔧', '🔨', '⚒️', '🛠️', '⛏️', '🪚', '🔩', '⚙️', '🪤', '🧱', '⛓️', '🧲', '🔫', '💣', '🧨', '🪓', '🔪', '🗡️', '⚔️', '🛡️', '🚬', '⚰️', '🪦', '⚱️', '🏺', '🔮', '📿', '🧿', '💈', '⚗️', '🔭', '🔬', '🕳️', '🩹', '🩺', '💊', '💉', '🩸', '🧬', '🦠', '🧫', '🧪', '🌡️', '🧹', '🧺', '🧻', '🚽', '🚰', '🚿', '🛁', '🛀', '🧼', '🪥', '🪒', '🧽', '🪣', '🧴', '🛎️', '🔑', '🗝️', '🚪', '🪑', '🛋️', '🛏️', '🛌', '🧸', '🪆', '🖼️', '🪞', '🪟', '🛍️', '🛒', '🎁', '🎈', '🎏', '🎀', '🪄', '🪅', '🎊', '🎉', '🎎', '🏮', '🎐', '🧧', '✉️', '📩', '📨', '📧', '💌', '📥', '📤', '📦', '🏷️', '📪', '📫', '📬', '📭', '📮', '📯', '📜', '📃', '📄', '📑', '🧾', '📊', '📈', '📉', '🗒️', '🗓️', '📆', '📅', '🗑️', '📇', '🗃️', '🗳️', '🗄️', '📋', '📁', '📂', '🗂️', '🗞️', '📰', '📓', '📔', '📒', '📕', '📗', '📘', '📙', '📚', '📖', '🔖', '🧷', '🔗', '📎', '🖇️', '📐', '📏', '🧮', '📌', '📍', '✂️', '🖊️', '🖋️', '✒️', '🖌️', '🖍️', '📝', '✏️', '🔍', '🔎', '🔏', '🔐', '🔒', '🔓'],
    'Symbols': ['❤️', '🧡', '💛', '💚', '💙', '💜', '🖤', '🤍', '🤎', '💔', '❣️', '💕', '💞', '💓', '💗', '💖', '💘', '💝', '💟', '☮️', '✝️', '☪️', '🕉️', '☸️', '✡️', '🔯', '🕎', '☯️', '☦️', '🛐', '⛎', '♈', '♉', '♊', '♋', '♌', '♍', '♎', '♏', '♐', '♑', '♒', '♓', '🆔', '⚛️', '🉑', '☢️', '☣️', '📴', '📳', '🈶', '🈚', '🈸', '🈺', '🈷️', '✴️', '🆚', '💮', '🉐', '㊙️', '㊗️', '🈴', '🈵', '🈹', '🈲', '🅰️', '🅱️', '🆎', '🆑', '🅾️', '🆘', '❌', '⭕', '🛑', '⛔', '📛', '🚫', '💯', '💢', '♨️', '🚷', '🚯', '🚳', '🚱', '🔞', '📵', '🚭', '❗', '❕', '❓', '❔', '‼️', '⁉️', '🔅', '🔆', '〽️', '⚠️', '🚸', '🔱', '⚜️', '🔰', '♻️', '✅', '🈯', '💹', '❇️', '✳️', '❎', '🌐', '💠', 'Ⓜ️', '🌀', '💤', '🏧', '🚾', '♿', '🅿️', '🛗', '🈳', '🈂️', '🛂', '🛃', '🛄', '🛅', '🚹', '🚺', '🚼', '⚧️', '🚻', '🚮', '🎦', '📶', '🈁', '🔣', '🔤', '🔡', '🔠', '🆖', '🆗', '🆙', '🆒', '🆕', '🆓', '0️⃣', '1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟', '🔢', '#️⃣', '*️⃣', '⏏️', '▶️', '⏸️', '⏯️', '⏹️', '⏺️', '⏭️', '⏮️', '⏩', '⏪', '⏫', '⏬', '◀️', '🔼', '🔽', '➡️', '⬅️', '⬆️', '⬇️', '↗️', '↘️', '↙️', '↖️', '↕️', '↔️', '↪️', '↩️', '⤴️', '⤵️', '🔀', '🔁', '🔂', '🔄', '🔃', '🎵', '🎶', '➕', '➖', '➗', '✖️', '🟰', '♾️', '💲', '💱', '™️', '©️', '®️', '〰️', '➰', '➿', '🔚', '🔙', '🔛', '🔝', '🔜', '✔️', '☑️', '🔘', '🔴', '🟠', '🟡', '🟢', '🔵', '🟣', '⚫', '⚪', '🟤', '🔺', '🔻', '🔸', '🔹', '🔶', '🔷', '🔳', '🔲', '▪️', '▫️', '◾', '◽', '◼️', '◻️', '🟥', '🟧', '🟨', '🟩', '🟦', '🟪', '⬛', '⬜', '🟫', '🔈', '🔇', '🔉', '🔊', '🔔', '🔕', '📣', '📢', '👁️‍🗨️', '💬', '💭', '🗯️', '♠️', '♣️', '♥️', '♦️', '🃏', '🎴', '🀄', '🕐', '🕑', '🕒', '🕓', '🕔', '🕕', '🕖', '🕗', '🕘', '🕙', '🕚', '🕛', '🕜', '🕝', '🕞', '🕟', '🕠', '🕡', '🕢', '🕣', '🕤', '🕥', '🕦', '🕧'],
    'Nature': ['🌵', '🎄', '🌲', '🌳', '🌴', '🪵', '🌱', '🌿', '☘️', '🍀', '🎍', '🪴', '🎋', '🍃', '🍂', '🍁', '🍄', '🌾', '💐', '🌷', '🌹', '🥀', '🪻', '🌺', '🌸', '🌼', '🌻', '🌞', '🌝', '🌛', '🌜', '🌚', '🌕', '🌖', '🌗', '🌘', '🌑', '🌒', '🌓', '🌔', '🌙', '🌎', '🌍', '🌏', '🪐', '💫', '⭐', '🌟', '✨', '⚡', '☄️', '💥', '🔥', '🌪️', '🌈', '☀️', '🌤️', '⛅', '🌥️', '☁️', '🌦️', '🌧️', '⛈️', '🌩️', '🌨️', '❄️', '☃️', '⛄', '🌬️', '💨', '💧', '💦', '☔', '☂️', '🌊', '🌫️'],
    'Flags': ['🏳️', '🏴', '🏴‍☠️', '🏁', '🚩', '🎌', '🏳️‍🌈', '🏳️‍⚧️', '🇺🇳', '🇦🇫', '🇦🇽', '🇦🇱', '🇩🇿', '🇦🇸', '🇦🇩', '🇦🇴', '🇦🇮', '🇦🇶', '🇦🇬', '🇦🇷', '🇦🇲', '🇦🇼', '🇦🇺', '🇦🇹', '🇦🇿', '🇧🇸', '🇧🇭', '🇧🇩', '🇧🇧', '🇧🇾', '🇧🇪', '🇧🇿', '🇧🇯', '🇧🇲', '🇧🇹', '🇧🇴', '🇧🇦', '🇧🇼', '🇧🇷', '🇮🇴', '🇻🇬', '🇧🇳', '🇧🇬', '🇧🇫', '🇧🇮', '🇰🇭', '🇨🇲', '🇨🇦', '🇮🇨', '🇨🇻', '🇧🇶', '🇰🇾', '🇨🇫', '🇹🇩', '🇨🇱', '🇨🇳', '🇨🇽', '🇨🇨', '🇨🇴', '🇰🇲', '🇨🇬', '🇨🇩', '🇨🇰', '🇨🇷', '🇨🇮', '🇭🇷', '🇨🇺', '🇨🇼', '🇨🇾', '🇨🇿', '🇩🇰', '🇩🇯', '🇩🇲', '🇩🇴', '🇪🇨', '🇪🇬', '🇸🇻', '🇬🇶', '🇪🇷', '🇪🇪', '🇸🇿', '🇪🇹', '🇪🇺', '🇫🇰', '🇫🇴', '🇫🇯', '🇫🇮', '🇫🇷', '🇬🇫', '🇵🇫', '🇹🇫', '🇬🇦', '🇬🇲', '🇬🇪', '🇩🇪', '🇬🇭', '🇬🇮', '🇬🇷', '🇬🇱', '🇬🇩', '🇬🇵', '🇬🇺', '🇬🇹', '🇬🇬', '🇬🇳', '🇬🇼', '🇬🇾', '🇭🇹', '🇭🇳', '🇭🇰', '🇭🇺', '🇮🇸', '🇮🇳', '🇮🇩', '🇮🇷', '🇮🇶', '🇮🇪', '🇮🇲', '🇮🇱', '🇮🇹', '🇯🇲', '🇯🇵', '🎌', '🇯🇪', '🇯🇴', '🇰🇿', '🇰🇪', '🇰🇮', '🇽🇰', '🇰🇼', '🇰🇬', '🇱🇦', '🇱🇻', '🇱🇧', '🇱🇸', '🇱🇷', '🇱🇾', '🇱🇮', '🇱🇹', '🇱🇺', '🇲🇴', '🇲🇬', '🇲🇼', '🇲🇾', '🇲🇻', '🇲🇱', '🇲🇹', '🇲🇭', '🇲🇶', '🇲🇷', '🇲🇺', '🇾🇹', '🇲🇽', '🇫🇲', '🇲🇩', '🇲🇨', '🇲🇳', '🇲🇪', '🇲🇸', '🇲🇦', '🇲🇿', '🇲🇲', '🇳🇦', '🇳🇷', '🇳🇵', '🇳🇱', '🇳🇨', '🇳🇿', '🇳🇮', '🇳🇪', '🇳🇬', '🇳🇺', '🇳🇫', '🇰🇵', '🇲🇰', '🇲🇵', '🇳🇴', '🇴🇲', '🇵🇰', '🇵🇼', '🇵🇸', '🇵🇦', '🇵🇬', '🇵🇾', '🇵🇪', '🇵🇭', '🇵🇳', '🇵🇱', '🇵🇹', '🇵🇷', '🇶🇦', '🇷🇪', '🇷🇴', '🇷🇺', '🇷🇼', '🇼🇸', '🇸🇲', '🇸🇹', '🇸🇦', '🇸🇳', '🇷🇸', '🇸🇨', '🇸🇱', '🇸🇬', '🇸🇽', '🇸🇰', '🇸🇮', '🇬🇸', '🇸🇧', '🇸🇴', '🇿🇦', '🇰🇷', '🇸🇸', '🇪🇸', '🇱🇰', '🇧🇱', '🇸🇭', '🇰🇳', '🇱🇨', '🇵🇲', '🇻🇨', '🇸🇩', '🇸🇷', '🇸🇪', '🇨🇭', '🇸🇾', '🇹🇼', '🇹🇯', '🇹🇿', '🇹🇭', '🇹🇱', '🇹🇬', '🇹🇰', '🇹🇴', '🇹🇹', '🇹🇳', '🇹🇷', '🇹🇲', '🇹🇨', '🇹🇻', '🇻🇮', '🇺🇬', '🇺🇦', '🇦🇪', '🇬🇧', '🏴󠁧󠁢󠁥󠁮󠁧󠁿', '🏴󠁧󠁢󠁳󠁣󠁴󠁿', '🏴󠁧󠁢󠁷󠁬󠁳󠁿', '🇺🇸', '🇺🇾', '🇺🇿', '🇻🇺', '🇻🇦', '🇻🇪', '🇻🇳', '🇼🇫', '🇪🇭', '🇾🇪', '🇿🇲', '🇿🇼']
};

function setupEmojiPicker() {
    const emojiBtn = document.getElementById('threadEmojiBtn');
    const popup = document.getElementById('emojiPickerPopup');
    
    if (!emojiBtn || !popup) return;
    
    // Render emoji picker with search and categories
    function renderEmojiPicker(searchTerm = '') {
        const categories = Object.keys(THREAD_EMOJIS);
        const normalizedSearch = searchTerm.toLowerCase().trim();
        
        let contentHtml = '';
        
        if (normalizedSearch) {
            // Search mode: show flat filtered results
            const allEmojis = [];
            for (const [category, emojis] of Object.entries(THREAD_EMOJIS)) {
                for (const emoji of emojis) {
                    // Simple matching - include if category matches or emoji is in search
                    if (category.toLowerCase().includes(normalizedSearch)) {
                        allEmojis.push(emoji);
                    }
                }
            }
            // Also do a basic emoji match for common terms
            const emojiKeywords = {
                'heart': ['❤️', '🧡', '💛', '💚', '💙', '💜', '🖤', '🤍', '🤎', '💔', '💕', '💖', '💗', '💘', '💝'],
                'smile': ['😀', '😊', '😄', '😁', '🙂', '😉', '😎', '🤗', '😇'],
                'sad': ['😢', '😭', '😞', '😔', '🥺', '😿'],
                'run': ['🏃', '🏃‍♂️', '🏃‍♀️', '🚴', '🚵'],
                'work': ['💼', '🏢', '💻', '📊', '📈', '📝', '✏️', '🔧', '⚙️'],
                'food': ['🍽️', '🍕', '🍔', '🍟', '🌮', '🍜', '🍣', '🥗', '🍎', '☕'],
                'gym': ['🏋️', '💪', '🏃', '🧘', '🤸'],
                'sleep': ['😴', '🛏️', '💤', '🌙', '😪'],
                'home': ['🏠', '🏡', '🏘️', '🛋️', '🏚️'],
                'travel': ['✈️', '🚗', '🚂', '🚢', '🏖️', '🗺️', '🧳'],
                'music': ['🎵', '🎶', '🎤', '🎧', '🎸', '🎹', '🎷', '🥁'],
                'movie': ['🎬', '🎥', '📽️', '🍿', '🎞️'],
                'book': ['📚', '📖', '📕', '📗', '📘', '📙', '📓'],
                'star': ['⭐', '🌟', '✨', '💫', '🌠'],
                'fire': ['🔥', '🔥', '💥', '🌋'],
                'check': ['✅', '✔️', '☑️', '✓'],
                'x': ['❌', '❎', '✖️'],
                'money': ['💰', '💵', '💴', '💶', '💷', '💳', '💸', '🤑'],
                'time': ['⏰', '⏱️', '⏲️', '🕐', '📅', '📆'],
                'phone': ['📱', '📲', '☎️', '📞'],
                'mail': ['📧', '✉️', '📩', '📨', '💌'],
                'idea': ['💡', '🧠', '💭', '🤔'],
                'party': ['🎉', '🎊', '🥳', '🎈', '🎁'],
                'health': ['🏥', '💊', '💉', '🩺', '🩹', '❤️‍🩹'],
            };
            
            for (const [keyword, emojis] of Object.entries(emojiKeywords)) {
                if (keyword.includes(normalizedSearch) || normalizedSearch.includes(keyword)) {
                    for (const emoji of emojis) {
                        if (!allEmojis.includes(emoji)) {
                            allEmojis.push(emoji);
                        }
                    }
                }
            }
            
            if (allEmojis.length > 0) {
                contentHtml = `
                    <div class="emoji-category">
                        <div class="emoji-category-title">Search Results</div>
                        <div class="emoji-grid">
                            ${allEmojis.slice(0, 64).map(emoji => `
                                <button class="emoji-option" data-emoji="${emoji}">${emoji}</button>
                            `).join('')}
                        </div>
                    </div>
                `;
            } else {
                contentHtml = '<div class="emoji-no-results">No emojis found</div>';
            }
        } else {
            // Category mode: show all categories
            contentHtml = categories.map(category => `
                <div class="emoji-category">
                    <div class="emoji-category-title">${category}</div>
                    <div class="emoji-grid">
                        ${THREAD_EMOJIS[category].map(emoji => `
                            <button class="emoji-option" data-emoji="${emoji}">${emoji}</button>
                        `).join('')}
                    </div>
                </div>
            `).join('');
        }
        
        popup.innerHTML = `
            <div class="emoji-search-container">
                <input type="text" class="emoji-search-input" placeholder="Search emojis..." value="${searchTerm}">
            </div>
            <div class="emoji-content">
                ${contentHtml}
            </div>
        `;
        
        // Re-attach search listener
        const searchInput = popup.querySelector('.emoji-search-input');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                renderEmojiPicker(e.target.value);
            });
            // Keep focus on search input
            if (searchTerm) {
                searchInput.focus();
                searchInput.setSelectionRange(searchInput.value.length, searchInput.value.length);
            }
        }
    }
    
    // Initial render
    renderEmojiPicker();
    
    // Toggle popup on button click
    emojiBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const wasVisible = popup.classList.contains('visible');
        popup.classList.toggle('visible');
        if (!wasVisible) {
            // Reset search and focus when opening
            renderEmojiPicker();
            setTimeout(() => {
                const searchInput = popup.querySelector('.emoji-search-input');
                if (searchInput) searchInput.focus();
            }, 50);
        }
    });
    
    // Handle emoji selection
    popup.addEventListener('click', async (e) => {
        const option = e.target.closest('.emoji-option');
        if (option) {
            const emoji = option.dataset.emoji;
            await saveThreadEmoji(emoji);
            popup.classList.remove('visible');
        }
    });
    
    // Close popup when clicking outside
    document.addEventListener('click', (e) => {
        if (!popup.contains(e.target) && e.target !== emojiBtn) {
            popup.classList.remove('visible');
        }
    });
}

async function saveThreadEmoji(emoji) {
    if (!state.currentThreadId) return;
    
    try {
        const response = await fetch(`/api/threads/${state.currentThreadId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ emoji })
        });
        if (response.ok) {
            updateThreadEmoji(emoji);
            // Update in threads list
            const thread = state.threads.find(t => t.thread_id === state.currentThreadId);
            if (thread) thread.emoji = emoji;
            renderThreadsList();
            showToast('Emoji saved');
        }
    } catch (error) {
        console.error('Failed to save thread emoji:', error);
    }
}

async function saveThreadTitle() {
    const titleEl = document.getElementById('currentThreadTitle');
    const newTitle = titleEl.value.trim() || 'Untitled';
    
    if (newTitle === state.currentThreadTitle) return;
    
    // Always save title to backend (even for threads without messages)
    // This prevents auto-rename from overwriting user's custom title
    try {
        const response = await fetch(`/api/threads/${state.currentThreadId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: newTitle })
        });
        if (response.ok) {
            state.currentThreadTitle = newTitle;
            showToast('Title saved');
        }
    } catch (error) {
        console.error('Failed to save thread title:', error);
        // Revert to previous title
        titleEl.value = state.currentThreadTitle;
    }
}

function showToast(message, isError = false) {
    // Remove any existing toast
    const existing = document.querySelector('.thread-saved-toast');
    if (existing) existing.remove();
    
    const toast = document.createElement('div');
    toast.className = 'thread-saved-toast';
    if (isError) {
        toast.style.background = 'var(--error)';
    }
    toast.textContent = message;
    document.body.appendChild(toast);
    
    // Remove after animation
    setTimeout(() => toast.remove(), 2000);
}

async function loadCurrentThreadInfo() {
    try {
        const response = await fetch('/api/threads');
        const data = await response.json();
        if (data.current_thread_id) {
            state.currentThreadId = data.current_thread_id;
        }
        // Get the title and message count of current thread from list if available
        const currentThread = (data.threads || []).find(t => t.thread_id === data.current_thread_id);
        if (currentThread) {
            updateThreadTitle(currentThread.title);
            state.threadHasMessages = currentThread.message_count > 0;
            
            // Restore model from thread's saved model binding
            if (currentThread.model_provider && currentThread.model_name) {
                state.tiles.chat.model = `${currentThread.model_provider}/${currentThread.model_name}`;
                
                // Find and update model display name
                for (const [name, config] of Object.entries(MODELS)) {
                    if (config.model === currentThread.model_name) {
                        updateCurrentChatModelDisplay(name);
                        break;
                    }
                }
            }
        } else {
            // Current thread not in list (empty thread) - check separately
            state.threadHasMessages = false;
            updateThreadTitle('New Conversation');
        }
        
        // Update usage displays now that we have the thread ID
        // Backend calculates costs - we just display
        loadChatUsage();
        updateToolUsageDisplay();
        loadDistillUsage();
        
        // If we have messages, load the history
        if (state.threadHasMessages && state.currentThreadId) {
            try {
                const historyResponse = await fetch('/api/history');
                const historyData = await historyResponse.json();
                if (historyData.history && historyData.history.length > 0) {
                    state.messages = historyData.history.map(m => ({
                        role: m.role,
                        content: m.content,
                        timestamp: m.timestamp,
                        type: m.type || 'message',
                        tool_calls: m.tool_calls || [],
                    }));
                    state.turnCount = state.messages.filter(m => m.role === 'assistant' && m.type !== 'thinking').length;
                    renderMessages();
                }
            } catch (e) {
                console.log('Could not load history:', e);
            }
        }
        
        // Load LLM logs for thread
        loadLLMLogs();
    } catch (error) {
        console.log('Could not load thread info:', error);
    }
}

// LLM Logs functionality
function toggleLogsSection() {
    const section = document.getElementById('llmLogsSection');
    section.classList.toggle('expanded');
    lucide.createIcons();
    
    // Load logs when expanded
    if (section.classList.contains('expanded')) {
        loadLLMLogs();
    }
}

// Usage section toggle
function toggleUsageSection() {
    const section = document.getElementById('usageSection');
    section.classList.toggle('expanded');
    lucide.createIcons();
}

async function loadLLMLogs() {
    if (!state.currentThreadId) return;
    
    const logsList = document.getElementById('llmLogsList');
    try {
        const response = await fetch(`/api/threads/${state.currentThreadId}/logs?limit=100`);
        const data = await response.json();
        
        if (!data.logs || data.logs.length === 0) {
            logsList.innerHTML = '<div class="empty-state">No logs yet</div>';
            return;
        }
        
        // Group logs by turn
        const turnGroups = groupLogsByTurn(data.logs);
        
        logsList.innerHTML = turnGroups.map(group => renderTurnGroup(group)).join('');
        lucide.createIcons();
    } catch (error) {
        console.error('Failed to load logs:', error);
        logsList.innerHTML = '<div class="empty-state">Failed to load logs</div>';
    }
}

// Handle real-time log entry from WebSocket
function handleLogEntry(entry) {
    const logsList = document.getElementById('llmLogsList');
    const logsSection = document.getElementById('llmLogsSection');
    
    // Only update if logs section exists
    if (!logsList) return;
    
    // Clear "No logs yet" message if present
    const emptyState = logsList.querySelector('.empty-state');
    if (emptyState) {
        logsList.innerHTML = '';
    }
    
    const turn = entry.turn || 0;
    
    // Find or create turn group
    let turnGroup = logsList.querySelector(`.turn-group[data-turn="${turn}"]`);
    
    if (!turnGroup) {
        // Create new turn group at the top (newest first)
        const time = new Date(entry.timestamp).toLocaleTimeString();
        const groupHtml = `
            <div class="turn-group" data-turn="${turn}">
                <div class="turn-header" onclick="toggleTurnGroup(this)">
                    <div class="turn-info">
                        <i data-lucide="chevron-right" class="turn-chevron"></i>
                        <span class="turn-number">Turn ${turn}</span>
                        <span class="turn-time">${time}</span>
                    </div>
                    <div class="turn-summary">
                        <span class="turn-req-count">0</span>req • <span class="turn-res-count">0</span>res<span class="turn-tool-count"></span>
                    </div>
                </div>
                <div class="turn-logs" style="display:block"></div>
            </div>
        `;
        
        // Insert at beginning or find correct position (descending order)
        const existingGroups = logsList.querySelectorAll('.turn-group');
        let inserted = false;
        for (const existing of existingGroups) {
            const existingTurn = parseInt(existing.dataset.turn);
            if (turn > existingTurn) {
                existing.before(document.createRange().createContextualFragment(groupHtml));
                inserted = true;
                break;
            }
        }
        if (!inserted) {
            logsList.insertAdjacentHTML('beforeend', groupHtml);
        }
        
        turnGroup = logsList.querySelector(`.turn-group[data-turn="${turn}"]`);
        lucide.createIcons({nodes: [turnGroup]});
    }
    
    // Add log entry to the turn group
    const turnLogs = turnGroup.querySelector('.turn-logs');
    const entryHtml = renderLogEntry(entry);
    turnLogs.insertAdjacentHTML('beforeend', entryHtml);
    
    // Update turn summary counts
    updateTurnSummary(turnGroup);
    
    // Auto-expand if logs section is open (for real-time visibility)
    if (logsSection && logsSection.classList.contains('expanded')) {
        // Keep the turn group expanded for real-time viewing
        turnGroup.classList.add('expanded');
        const chevron = turnGroup.querySelector('.turn-chevron');
        if (chevron) {
            chevron.setAttribute('data-lucide', 'chevron-down');
            lucide.createIcons({nodes: [turnGroup]});
        }
    }
}

// Update turn group summary after adding a log entry
function updateTurnSummary(turnGroup) {
    const logs = turnGroup.querySelector('.turn-logs');
    const requests = logs.querySelectorAll('.log-request').length;
    const responses = logs.querySelectorAll('.log-response, .log-error').length;
    const tools = logs.querySelectorAll('.log-tool').length;
    const hasError = logs.querySelectorAll('.log-error, .log-tool-error').length > 0;
    
    const reqCount = turnGroup.querySelector('.turn-req-count');
    const resCount = turnGroup.querySelector('.turn-res-count');
    const toolCount = turnGroup.querySelector('.turn-tool-count');
    
    if (reqCount) reqCount.textContent = requests;
    if (resCount) resCount.textContent = responses;
    if (toolCount) toolCount.textContent = tools > 0 ? ` • ${tools}🔧` : '';
    
    // Update error indicator
    if (hasError) {
        turnGroup.classList.add('has-error');
        const summary = turnGroup.querySelector('.turn-summary');
        if (summary && !summary.textContent.includes('❌')) {
            summary.insertAdjacentHTML('beforeend', ' • ❌');
        }
    }
}

function groupLogsByTurn(logs) {
    // Group logs by turn number
    const groups = new Map();
    
    for (const log of logs) {
        const turn = log.turn || 0;
        if (!groups.has(turn)) {
            groups.set(turn, {
                turn: turn,
                logs: [],
                timestamp: log.timestamp
            });
        }
        groups.get(turn).logs.push(log);
    }
    
    // Convert to array and sort by turn (descending - newest first)
    return Array.from(groups.values()).sort((a, b) => b.turn - a.turn);
}

function renderTurnGroup(group) {
    const time = new Date(group.timestamp).toLocaleTimeString();
    const logCount = group.logs.length;
    
    // Calculate summary stats for the turn
    const requests = group.logs.filter(l => l.type === 'request').length;
    const responses = group.logs.filter(l => l.type === 'response').length;
    const tools = group.logs.filter(l => l.type === 'tool_execution').length;
    const hasError = group.logs.some(l => l.error);
    
    const logsHtml = group.logs.map(log => renderLogEntry(log)).join('');
    
    return `
        <div class="turn-group ${hasError ? 'has-error' : ''}" data-turn="${group.turn}">
            <div class="turn-header" onclick="toggleTurnGroup(this)">
                <div class="turn-info">
                    <i data-lucide="chevron-right" class="turn-chevron"></i>
                    <span class="turn-number">Turn ${group.turn}</span>
                    <span class="turn-time">${time}</span>
                </div>
                <div class="turn-summary">
                    ${requests}req • ${responses}res${tools > 0 ? ` • ${tools}🔧` : ''}
                    ${hasError ? ' • ❌' : ''}
                </div>
            </div>
            <div class="turn-logs" style="display:none">
                ${logsHtml}
            </div>
        </div>
    `;
}

function toggleTurnGroup(header) {
    const group = header.closest('.turn-group');
    const logs = group.querySelector('.turn-logs');
    const chevron = header.querySelector('.turn-chevron');
    
    const isExpanded = logs.style.display !== 'none';
    logs.style.display = isExpanded ? 'none' : 'block';
    group.classList.toggle('expanded', !isExpanded);
    
    // Update chevron icon
    if (chevron) {
        chevron.setAttribute('data-lucide', isExpanded ? 'chevron-right' : 'chevron-down');
        lucide.createIcons();
    }
}

function renderLogEntry(log) {
    const time = new Date(log.timestamp).toLocaleTimeString();
    const logJson = JSON.stringify(log, null, 2);
    const logId = `log-${log.request_id || log.timestamp}-${Math.random().toString(36).substr(2, 9)}`;
    
    if (log.type === 'request') {
        return `
            <div class="log-entry log-request" onclick="toggleLogDetails(this)" data-log-id="${logId}">
                <div class="log-header">
                    <span class="log-type">📤 Request</span>
                    <span class="log-time">${time}</span>
                    <button class="log-copy-btn" onclick="copyLogEntry(event, '${logId}')" title="Copy log entry">
                        <i data-lucide="copy" class="log-copy-icon"></i>
                    </button>
                </div>
                <div class="log-summary">
                    ${log.provider}/${log.model} • ${log.message_count} msgs • ${log.tools_count} tools
                </div>
                <div class="log-details" style="display:none">
                    <div class="log-detail-section">
                        <strong>System Prompt (${log.system_prompt_length} chars):</strong>
                        <pre>${escapeHtml(log.system_prompt || 'None')}</pre>
                    </div>
                    <div class="log-detail-section">
                        <strong>Messages:</strong>
                        <pre>${JSON.stringify(log.messages, null, 2)}</pre>
                    </div>
                    <div class="log-detail-section">
                        <strong>Tools (${log.tools_count}):</strong>
                        <pre>${log.tool_names ? log.tool_names.join(', ') : 'None'}</pre>
                    </div>
                </div>
                <script type="application/json" class="log-data">${escapeHtml(logJson)}</script>
            </div>
        `;
    } else if (log.type === 'response') {
        const hasError = log.error;
        const statusClass = hasError ? 'log-error' : 'log-response';
        const statusIcon = hasError ? '❌' : '📥';
        return `
            <div class="log-entry ${statusClass}" onclick="toggleLogDetails(this)" data-log-id="${logId}">
                <div class="log-header">
                    <span class="log-type">${statusIcon} Response</span>
                    <span class="log-time">${time}</span>
                    <button class="log-copy-btn" onclick="copyLogEntry(event, '${logId}')" title="Copy log entry">
                        <i data-lucide="copy" class="log-copy-icon"></i>
                    </button>
                </div>
                <div class="log-summary">
                    ${log.stop_reason} • ${log.content_length} chars • ${log.usage?.input_tokens || 0}/${log.usage?.output_tokens || 0} tokens
                    ${log.tool_calls?.length ? ` • ${log.tool_calls.length} tool calls` : ''}
                </div>
                <div class="log-details" style="display:none">
                    ${hasError ? `<div class="log-detail-section log-error-msg"><strong>Error:</strong> ${escapeHtml(log.error)}</div>` : ''}
                    <div class="log-detail-section">
                        <strong>Content:</strong>
                        <pre>${escapeHtml(log.content || 'None')}</pre>
                    </div>
                    ${log.tool_calls?.length ? `
                        <div class="log-detail-section">
                            <strong>Tool Calls:</strong>
                            <pre>${JSON.stringify(log.tool_calls, null, 2)}</pre>
                        </div>
                    ` : ''}
                    <div class="log-detail-section">
                        <strong>Usage:</strong> ${log.usage?.input_tokens || 0} input, ${log.usage?.output_tokens || 0} output
                    </div>
                </div>
                <script type="application/json" class="log-data">${escapeHtml(logJson)}</script>
            </div>
        `;
    } else if (log.type === 'tool_execution') {
        const hasError = log.error;
        const statusIcon = hasError ? '⚠️' : '🔧';
        return `
            <div class="log-entry log-tool ${hasError ? 'log-tool-error' : ''}" onclick="toggleLogDetails(this)" data-log-id="${logId}">
                <div class="log-header">
                    <span class="log-type">${statusIcon} ${log.tool_name}</span>
                    <span class="log-time">${log.duration_ms}ms</span>
                    <button class="log-copy-btn" onclick="copyLogEntry(event, '${logId}')" title="Copy log entry">
                        <i data-lucide="copy" class="log-copy-icon"></i>
                    </button>
                </div>
                <div class="log-summary">
                    ${log.result_length} chars result
                </div>
                <div class="log-details" style="display:none">
                    <div class="log-detail-section">
                        <strong>Arguments:</strong>
                        <pre>${JSON.stringify(log.arguments, null, 2)}</pre>
                    </div>
                    <div class="log-detail-section">
                        <strong>Result:</strong>
                        <pre>${escapeHtml(log.result_preview || 'None')}</pre>
                    </div>
                    ${hasError ? `<div class="log-detail-section log-error-msg"><strong>Error:</strong> ${escapeHtml(log.error)}</div>` : ''}
                </div>
                <script type="application/json" class="log-data">${escapeHtml(logJson)}</script>
            </div>
        `;
    }
    return '';
}

// Copy log entry to clipboard
function copyLogEntry(event, logId) {
    event.stopPropagation(); // Don't toggle details
    const logEntry = document.querySelector(`[data-log-id="${logId}"]`);
    if (!logEntry) return;
    
    const logDataEl = logEntry.querySelector('.log-data');
    if (!logDataEl) return;
    
    try {
        const logData = JSON.parse(logDataEl.textContent);
        navigator.clipboard.writeText(JSON.stringify(logData, null, 2));
        showToast('Log copied to clipboard');
    } catch (e) {
        console.error('Failed to copy log:', e);
        showToast('Failed to copy log', true);
    }
}

function toggleLogDetails(element) {
    const details = element.querySelector('.log-details');
    if (details) {
        details.style.display = details.style.display === 'none' ? 'block' : 'none';
    }
}


