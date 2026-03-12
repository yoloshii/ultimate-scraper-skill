"""WebMCP extraction via Chrome 146+ navigator.modelContext API (E5).

WebMCP allows pages to expose structured tools that agents can discover and call.
This module injects an interception layer and provides helpers for tool discovery
and execution.

Requirements:
- Chrome 146+ (chrome-dev, chrome-beta, or chrome-canary)
- --enable-features=WebMCPTesting launch flag
- Only works with CloakBrowser path (NOT Patchright — causes ERR_NAME_NOT_RESOLVED)
"""

# Ported from browser-use/scripts/browser_engine.py (WEBMCP_INIT_SCRIPT)
WEBMCP_INIT_SCRIPT = """
(() => {
    // Initialize WebMCP interception layer
    window.__webmcp = { tools: {}, available: false, declarative: {} };

    if (typeof navigator.modelContext === 'undefined') return;

    window.__webmcp.available = true;

    // --- Intercept imperative tool registrations ---

    const origRegister = navigator.modelContext.registerTool.bind(navigator.modelContext);
    navigator.modelContext.registerTool = function(tool) {
        window.__webmcp.tools[tool.name] = {
            name: tool.name,
            description: tool.description || '',
            inputSchema: tool.inputSchema || {},
            annotations: tool.annotations || {},
            _hasExecute: typeof tool.execute === 'function',
            _ref: tool,
        };
        return origRegister(tool);
    };

    const origProvide = navigator.modelContext.provideContext.bind(navigator.modelContext);
    navigator.modelContext.provideContext = function(options) {
        window.__webmcp.tools = {};
        for (const tool of (options?.tools || [])) {
            window.__webmcp.tools[tool.name] = {
                name: tool.name,
                description: tool.description || '',
                inputSchema: tool.inputSchema || {},
                annotations: tool.annotations || {},
                _hasExecute: typeof tool.execute === 'function',
                _ref: tool,
            };
        }
        return origProvide(options);
    };

    const origUnregister = navigator.modelContext.unregisterTool.bind(navigator.modelContext);
    navigator.modelContext.unregisterTool = function(name) {
        delete window.__webmcp.tools[name];
        return origUnregister(name);
    };

    const origClear = navigator.modelContext.clearContext.bind(navigator.modelContext);
    navigator.modelContext.clearContext = function() {
        window.__webmcp.tools = {};
        return origClear();
    };

    // --- Scan declarative tools (forms with toolname attribute) ---
    const scanDeclarativeForms = () => {
        window.__webmcp.declarative = {};
        document.querySelectorAll('form[toolname]').forEach(form => {
            const name = form.getAttribute('toolname');
            const desc = form.getAttribute('tooldescription') || '';
            const autoSubmit = form.hasAttribute('toolautosubmit');
            const schema = { type: 'object', properties: {}, required: [] };

            form.querySelectorAll('input, select, textarea').forEach(el => {
                if (el.type === 'submit' || el.type === 'hidden') return;
                const paramName = el.getAttribute('toolparamtitle') || el.name;
                if (!paramName) return;

                const paramDesc = el.getAttribute('toolparamdescription')
                    || el.labels?.[0]?.textContent?.trim()
                    || el.getAttribute('aria-description') || '';

                let prop = { description: paramDesc };

                if (el.tagName === 'SELECT') {
                    prop.type = 'string';
                    prop.enum = [];
                    prop.oneOf = [];
                    el.querySelectorAll('option').forEach(opt => {
                        if (opt.value) {
                            prop.enum.push(opt.value);
                            prop.oneOf.push({ const: opt.value, title: opt.textContent.trim() });
                        }
                    });
                } else if (el.type === 'checkbox') {
                    prop.type = 'boolean';
                } else if (el.type === 'number' || el.type === 'range') {
                    prop.type = 'number';
                } else if (el.type === 'radio') {
                    if (!schema.properties[paramName]) {
                        prop.type = 'string';
                        prop.enum = [];
                    } else {
                        prop = schema.properties[paramName];
                    }
                    if (el.value && !prop.enum.includes(el.value)) {
                        prop.enum.push(el.value);
                    }
                } else {
                    prop.type = 'string';
                }

                schema.properties[paramName] = prop;
                if (el.required && !schema.required.includes(paramName)) {
                    schema.required.push(paramName);
                }
            });

            window.__webmcp.declarative[name] = {
                name: name,
                description: desc,
                inputSchema: schema,
                autoSubmit: autoSubmit,
                _formSelector: form.id ? '#' + CSS.escape(form.id)
                    : 'form[toolname="' + CSS.escape(name) + '"]',
                _type: 'declarative',
            };
        });
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', scanDeclarativeForms);
    } else {
        scanDeclarativeForms();
    }

    window.__webmcp.rescanDeclarative = scanDeclarativeForms;

    // --- Expose execute helper ---
    window.__webmcp.executeTool = async (name, args) => {
        const imp = window.__webmcp.tools[name];
        if (imp && imp._ref && typeof imp._ref.execute === 'function') {
            return await imp._ref.execute(args);
        }
        const decl = window.__webmcp.declarative[name];
        if (decl) {
            const form = document.querySelector(decl._formSelector);
            if (!form) return { error: 'Form not found for declarative tool: ' + name };
            for (const [key, value] of Object.entries(args || {})) {
                const el = form.querySelector('[name="' + CSS.escape(key) + '"]')
                    || form.querySelector('[toolparamtitle="' + CSS.escape(key) + '"]');
                if (!el) continue;
                if (el.tagName === 'SELECT') {
                    el.value = value;
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                } else if (el.type === 'checkbox') {
                    el.checked = !!value;
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                } else if (el.type === 'radio') {
                    const radio = form.querySelector(
                        'input[name="' + CSS.escape(key) + '"][value="' + CSS.escape(String(value)) + '"]'
                    );
                    if (radio) { radio.checked = true; radio.dispatchEvent(new Event('change', { bubbles: true })); }
                } else {
                    const nativeSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value'
                    )?.set || Object.getOwnPropertyDescriptor(
                        window.HTMLTextAreaElement.prototype, 'value'
                    )?.set;
                    if (nativeSetter) nativeSetter.call(el, String(value));
                    else el.value = String(value);
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }
            if (decl.autoSubmit || true) {
                const submitBtn = form.querySelector('[type="submit"]') || form.querySelector('button:not([type])');
                if (submitBtn) submitBtn.click();
                else form.requestSubmit();
            }
            return { content: [{ type: 'text', text: 'Form submitted for tool: ' + name }] };
        }
        return { error: 'Tool not found: ' + name };
    };
})();
"""


async def inject_webmcp(context) -> None:
    """Inject WebMCP interception script into browser context."""
    await context.add_init_script(WEBMCP_INIT_SCRIPT)


async def discover_tools(page) -> dict:
    """Discover available WebMCP tools on the page.

    Returns:
        Dict with 'available' bool and 'tools' dict of discovered tools.
    """
    return await page.evaluate("""() => {
        if (!window.__webmcp) return { available: false, tools: {} };

        // Rescan declarative forms
        if (window.__webmcp.rescanDeclarative) window.__webmcp.rescanDeclarative();

        const all = {};

        // Imperative tools
        for (const [name, tool] of Object.entries(window.__webmcp.tools || {})) {
            all[name] = {
                name: tool.name,
                description: tool.description,
                inputSchema: tool.inputSchema,
                type: 'imperative',
            };
        }

        // Declarative tools
        for (const [name, tool] of Object.entries(window.__webmcp.declarative || {})) {
            all[name] = {
                name: tool.name,
                description: tool.description,
                inputSchema: tool.inputSchema,
                type: 'declarative',
            };
        }

        return {
            available: window.__webmcp.available,
            tools: all,
        };
    }""")


async def execute_tool(page, tool_name: str, args: dict) -> dict:
    """Execute a WebMCP tool on the page.

    Args:
        page: Playwright page object
        tool_name: Name of the tool to execute
        args: Arguments to pass to the tool

    Returns:
        Tool execution result dict.
    """
    return await page.evaluate(
        "([name, a]) => window.__webmcp.executeTool(name, a)",
        [tool_name, args]
    )
