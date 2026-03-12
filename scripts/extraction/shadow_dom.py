"""Shadow DOM piercing helpers for browser tiers.

Provides deepQuery/deepQueryAll that traverse shadow roots recursively.
Ported from browser-use/scripts/actions.py.
"""

# Minified JS that defines deepQuery and deepQueryAll globally.
# These traverse shadow DOM boundaries recursively.
DEEP_QUERY_JS = (
    "var deepQuery=function(sel,root=document){"
    "const el=root.querySelector(sel);if(el)return el;"
    "for(const h of root.querySelectorAll('*')){"
    "if(h.shadowRoot){const f=deepQuery(sel,h.shadowRoot);if(f)return f;}}"
    "return null;};"
    "var deepQueryAll=function(sel,root=document){"
    "const r=[...root.querySelectorAll(sel)];"
    "for(const h of root.querySelectorAll('*')){"
    "if(h.shadowRoot)r.push(...deepQueryAll(sel,h.shadowRoot));}"
    "return r;}"
)
