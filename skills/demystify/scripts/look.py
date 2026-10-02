#!/usr/bin/env python3
"""Render an SVG or HTML file in a local browser, save screenshots, and measure the layout.

A diagram or a page can be wrong in ways that the source does not show: text
that leaves its box, labels that overlap, a script that fails, a page that
scrolls sideways on a phone. This script renders the file in a Chrome-family
browser (Chrome, Chromium, Edge, Brave), measures those faults, and saves
screenshots for you to look at.

Usage:
    look.py diagram.svg
    look.py page.html --mobile

Options:
    --out DIR         folder for the screenshots (default: review/ next to the file)
    --mobile          HTML only: also render at phone width (360 px)
    --width N         HTML only: width of the window in px (default 1280, smallest 320)
    --do JS           HTML only: run this JavaScript in the page, then save one more screenshot.
                      Use it to see a state that is not the state at the start. Repeat it for more states.
    --print JS        HTML only: print the value of this JavaScript expression in the page.
                      Use it to compare the model of the page with the source. Repeat it for more values.
    --zoom X,Y,W,H    SVG only: also save an enlarged picture of one region, to read small text
    --json            print the report as JSON

Exit status:
    0  rendered, no errors
    1  rendered, errors found
    2  not rendered (no browser, or the browser failed): nothing was looked at

Standard library only. Python 3.8 or later.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ElementTree
from html.parser import HTMLParser
from pathlib import Path

sys.dont_write_bytecode = True  # do not leave __pycache__ in the skill folder

from _common import find_browser  # noqa: E402

DESKTOP_WIDTH = 1280
DESKTOP_HEIGHT = 900
DESKTOP_MAX_SLICES = 6
PHONE_WIDTH = 360
PHONE_HEIGHT = 780
PHONE_COLUMNS = 4  # screens side by side in one picture
PHONE_MAX_SCREENS = 8
SVG_MAX_WIDTH = 2000
REPORT_ID = "__demystify_report__"
PROBE_ID = "__demystify_probe__"
TEMPLATE_RE = re.compile(r"\bEDIT\b")  # the templates mark each sample text with this word

# Collects script errors. It goes first in the page, on one line, so that line numbers do not move.
ERROR_COLLECTOR = (
    "<script>window.__demystifyErrors=[];"
    "window.addEventListener('error',function(e){var m=e.message?(e.message+(e.lineno?' (line '+e.lineno+')':'')):"
    "('could not load '+((e.target&&(e.target.src||e.target.href))||'a resource'));"
    "window.__demystifyErrors.push(m);},true);"
    "window.addEventListener('unhandledrejection',function(e){window.__demystifyErrors.push("
    "'unhandled promise rejection: '+(e.reason&&e.reason.message?e.reason.message:e.reason));});</script>"
)

# Lets a screenshot show a part of the page lower down: open the copy with #y900 to scroll 900 px.
SCROLL_TO_HASH = (
    "<script>window.addEventListener('load',function(){var y=parseInt((location.hash||'').slice(2),10)||0;"
    "if(y){document.documentElement.style.scrollBehavior='auto';window.scrollTo(0,y);}});</script>"
)


# A screenshot must not catch a transition half-way, so the copies of the page have no motion.
NO_MOTION = (
    "<style>*,*::before,*::after{transition-duration:0s!important;transition-delay:0s!important;"
    "animation-duration:0s!important;animation-delay:0s!important;scroll-behavior:auto!important}</style>"
)


def probe_script(action: str, prints=()) -> str:
    """Runs the code of --do after the page loads, then gets the value of each --print expression.

    It writes what occurred into the page as JSON: the error of the action, the values, and the size
    of the page in that state.
    """
    job = json.dumps({"action": action, "prints": list(prints)}).replace("</", "<\\/")
    return (
        "<script>window.addEventListener('load',function(){var job=" + job + ",out={error:'',values:[]};"
        "function text(v){if(typeof v==='string')return v;"
        "try{var s=JSON.stringify(v);return s===undefined?String(v):s;}catch(e){return String(v);}}"
        "function finish(){var de=document.documentElement;"
        "out.page=[de.scrollWidth,Math.max(de.scrollHeight,document.body?document.body.scrollHeight:0)];"
        "out.content=document.body?Math.round(document.body.getBoundingClientRect().height):0;"
        "var t=JSON.stringify(out),s=document.createElement('script');s.type='application/json';s.id='" + PROBE_ID + "';"
        "s.textContent=t.replace(/</g,'\\\\u003c');document.body.appendChild(s);"
        "if(window.parent!==window){try{window.parent.postMessage({demystifyProbe:t},'*');}catch(e){}}}"
        "if(job.action){try{(0,eval)(job.action);}catch(e){out.error=(e&&e.message)||String(e);}}"
        "var chain=Promise.resolve();"
        "job.prints.forEach(function(code){chain=chain.then(function(){return (0,eval)(code);})"
        ".then(function(v){out.values.push({value:text(v)});},"
        "function(e){out.values.push({error:(e&&e.message)||String(e)});});});"
        "chain.then(function(){setTimeout(finish,200);});});</script>"
    )

AUDIT_JS = r"""
(function () {
  var REPORT_ID = '__demystify_report__';
  var errs = window.__demystifyErrors || (window.__demystifyErrors = []);

  function shown(el) {
    for (var n = el; n && n.nodeType === 1; n = n.parentElement) {
      var cs = getComputedStyle(n);
      if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return false;
    }
    return true;
  }
  function words(el) {
    var t = (el.textContent || '').replace(/\s+/g, ' ').trim();
    return t.length > 48 ? t.slice(0, 47) + '…' : t;
  }
  function name(el) {
    var s = el.tagName.toLowerCase();
    if (el.id) s += '#' + el.id;
    else if (el.classList && el.classList.length) s += '.' + el.classList[0];
    return s;
  }
  function box(el) {
    var r = el.getBoundingClientRect();
    return { l: r.left, t: r.top, r: r.right, b: r.bottom, w: r.width, h: r.height };
  }
  function area(b) { return Math.max(0, b.w) * Math.max(0, b.h); }
  function overlap(a, b) {
    var w = Math.min(a.r, b.r) - Math.max(a.l, b.l), h = Math.min(a.b, b.b) - Math.max(a.t, b.t);
    return w > 0 && h > 0 ? w * h : 0;
  }
  function ownText(el) {
    for (var i = 0; i < el.childNodes.length; i++) {
      var n = el.childNodes[i];
      if (n.nodeType === 3 && n.textContent.trim()) return true;
    }
    return false;
  }
  function add(list, rule, detail, limit) {
    var count = 0;
    for (var i = 0; i < list.length; i++) if (list[i].rule === rule) count++;
    if (count < (limit || 8)) list.push({ rule: rule, detail: detail });
  }

  function auditSvg(svg, R, index, total) {
    var canvas = box(svg);
    if (canvas.w < 1 || canvas.h < 1) return;
    var which = total > 1 ? 'picture ' + (index + 1) + ' of ' + total : 'the drawing';
    var texts = [].slice.call(svg.querySelectorAll('text')).filter(shown)
      .map(function (t) { return { el: t, b: box(t) }; })
      .filter(function (x) { return x.b.w > 0.5 && x.b.h > 0.5; });
    var rects = [].slice.call(svg.querySelectorAll('rect')).filter(shown)
      .map(function (r) { return box(r); })
      .filter(function (b) { return b.w > 4 && b.h > 4 && area(b) < area(canvas) * 0.9; });
    R.info.svgTexts = (R.info.svgTexts || 0) + texts.length;

    texts.forEach(function (x) {
      var b = x.b;
      var out = [['left', canvas.l - b.l], ['top', canvas.t - b.t], ['right', b.r - canvas.r], ['bottom', b.b - canvas.b]]
        .filter(function (side) { return side[1] > 2; })
        .map(function (side) { return 'at the ' + side[0] + ' by ' + Math.ceil(side[1]) + ' px'; });
      if (out.length) {
        add(R.errors, 'text-outside-canvas', '"' + words(x.el) + '" leaves ' + which + ' ' + out.join(' and '));
      }
      var size = parseFloat(getComputedStyle(x.el).fontSize);
      var view = svg.viewBox && svg.viewBox.baseVal && svg.viewBox.baseVal.width ? svg.viewBox.baseVal.width : 0;
      var shownSize = view ? size * canvas.w / view : size;
      if (shownSize < 11.5) add(R.warnings, 'tiny-text', '"' + words(x.el) + '" in ' + which + ' is ' + shownSize.toFixed(1) + ' px: text in a picture is 12 px or larger', 5);
      var cx = (b.l + b.r) / 2, cy = (b.t + b.b) / 2, home = null;
      rects.forEach(function (q) {
        if (cx >= q.l && cx <= q.r && cy >= q.t && cy <= q.b && (!home || area(q) < area(home))) home = q;
      });
      if (home && (b.l < home.l - 1.5 || b.r > home.r + 1.5 || b.t < home.t - 1.5 || b.b > home.b + 1.5)) {
        var over = Math.max(home.l - b.l, b.r - home.r, home.t - b.t, b.b - home.b);
        add(R.errors, 'text-overflows-box', '"' + words(x.el) + '" is ' + Math.ceil(over) + ' px outside its box');
      }
    });
    for (var i = 0; i < texts.length; i++) {
      for (var j = i + 1; j < texts.length; j++) {
        var a = texts[i].b, c = texts[j].b;
        if (overlap(a, c) > 0.15 * Math.min(area(a), area(c))) {
          add(R.errors, 'text-overlap', '"' + words(texts[i].el) + '" overlaps "' + words(texts[j].el) + '"');
        }
      }
    }
    texts.forEach(function (x) {
      var count = (x.el.textContent || '').trim().split(/\s+/).length;
      if (count > 25) add(R.warnings, 'long-label', '"' + words(x.el) + '" has ' + count + ' words: a label has 6 or fewer, and a headline or a note is one sentence of 25 or fewer', 5);
    });
    // A shape that is completely outside the drawing is usually a typing error in its coordinates.
    [].slice.call(svg.querySelectorAll('path, rect, circle, ellipse, line, polyline, polygon')).forEach(function (el) {
      if (el.closest('defs, marker, symbol, clipPath, mask, pattern') || !shown(el)) return;
      var b = box(el);
      if (el.tagName.toLowerCase() === 'path' && (el.getAttribute('d') || '').trim().length > 3 && el.getTotalLength() === 0) {
        add(R.errors, 'broken-path', 'a path draws nothing, so its d data is not valid: "' +
          el.getAttribute('d').trim().slice(0, 40) + '"', 5);
        return;
      }
      if (b.w < 0.5 && b.h < 0.5) return;
      if (b.r < canvas.l - 1 || b.l > canvas.r + 1 || b.b < canvas.t - 1 || b.t > canvas.b + 1) {
        add(R.errors, 'shape-outside-canvas', 'a ' + el.tagName.toLowerCase() + ' is completely outside the drawing (' +
          Math.round(b.l - canvas.l) + ', ' + Math.round(b.t - canvas.t) + '): check its coordinates', 5);
      }
    });
  }

  function parseColor(s) {
    var m = /^rgba?\(([^)]+)\)$/.exec(s || '');
    if (!m) return null;
    var p = m[1].split(/[,\s\/]+/).filter(Boolean).map(parseFloat);
    if (p.length < 3 || p.some(isNaN)) return null;
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  }
  function luminance(c) {
    function f(v) { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  }
  function backgroundOf(el) {
    for (var n = el; n && n.nodeType === 1; n = n.parentElement) {
      var cs = getComputedStyle(n);
      if (cs.backgroundImage && cs.backgroundImage !== 'none') return null;
      var c = parseColor(cs.backgroundColor);
      if (c && c.a >= 0.99) return c;
      if (c && c.a > 0.01) return null;
    }
    return { r: 255, g: 255, b: 255, a: 1 };
  }

  function overflowCheck(R, when) {
    var de = document.documentElement, vw = window.innerWidth;
    if (de.scrollWidth <= vw + 1) return;
    var past = [];
    var all = document.body ? document.body.querySelectorAll('*') : [];
    for (var i = 0; i < all.length && past.length < 3; i++) {
      var r = all[i].getBoundingClientRect();
      if (r.width > 0 && r.right > vw + 1 && shown(all[i])) past.push(name(all[i]));
    }
    add(R.errors, 'horizontal-overflow', 'the page is ' + de.scrollWidth + ' px wide in a ' + vw + ' px window' +
      (when ? ' ' + when : '') + (past.length ? '; past the edge: ' + past.join(', ') : ''), 2);
  }

  function auditHtml(R) {
    var de = document.documentElement;
    R.info.viewport = [window.innerWidth, window.innerHeight];
    R.info.page = [de.scrollWidth, Math.max(de.scrollHeight, document.body ? document.body.scrollHeight : 0)];
    R.info.content = document.body ? Math.round(document.body.getBoundingClientRect().height) : 0;
    overflowCheck(R, '');
    var all = document.body ? [].slice.call(document.body.querySelectorAll('*')) : [];
    all.forEach(function (el) {
      if (el.closest('svg') || !ownText(el) || !shown(el)) return;
      var cs = getComputedStyle(el);
      if ((cs.overflowX === 'hidden' || cs.overflowX === 'clip') && el.scrollWidth > el.clientWidth + 1) {
        add(R.warnings, 'clipped-text', '"' + words(el) + '" is cut off in ' + name(el), 5);
      }
      var size = parseFloat(cs.fontSize);
      if (size < 12) add(R.warnings, 'tiny-text', '"' + words(el) + '" is ' + size + ' px', 5);
      var fg = parseColor(cs.color), bg = backgroundOf(el);
      if (fg && bg && fg.a >= 0.99) {
        var l1 = luminance(fg), l2 = luminance(bg);
        var ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
        var large = size >= 24 || (size >= 18.66 && parseInt(cs.fontWeight, 10) >= 700);
        if (ratio < (large ? 3 : 4.5)) {
          add(R.warnings, 'low-contrast', '"' + words(el) + '" has contrast ' + ratio.toFixed(1) + ' (needs ' + (large ? '3' : '4.5') + ')', 5);
        }
      }
    });
    var leftovers = [];
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (var node = walker.nextNode(); node; node = walker.nextNode()) {
      var parent = node.parentElement;
      if (!parent || parent.closest('script, style, template') || !/\bEDIT\b/.test(node.textContent)) continue;
      leftovers.push(node.textContent.replace(/\s+/g, ' ').trim().slice(0, 60));
    }
    R.info.templateText = leftovers;
    R.info.controls = document.querySelectorAll(
      'button, input, select, textarea, summary, [role=button], [role=slider], [role=tab]').length;
  }

  function fire(el, type) { el.dispatchEvent(new Event(type, { bubbles: true })); }
  // The height of the content. The scroll height is no use here: on a short page it is the height of the window.
  function contentHeight() { return document.body ? Math.round(document.body.getBoundingClientRect().height) : 0; }
  function smoke(R) {
    var count = 0;
    function attempt(el, action) {
      if (el.disabled || !shown(el)) return;
      // A part that opens and closes changes the height of the page on purpose.
      var opens = el.tagName.toLowerCase() === 'summary' || el.hasAttribute('aria-expanded') || el.hasAttribute('aria-controls');
      var before = contentHeight();
      try { action(); count++; } catch (e) { errs.push('using ' + name(el) + ': ' + e.message); return; }
      var change = contentHeight() - before;
      if (!opens && Math.abs(change) > 2) {
        var label = words(el);
        add(R.warnings, 'page-jumps', 'the page became ' + Math.abs(change) + ' px ' + (change > 0 ? 'higher' : 'lower') +
          ' when the check used ' + name(el) + (label ? ' ("' + label + '")' : '') +
          ': give the area that changes a fixed size', 3);
      }
    }
    [].slice.call(document.querySelectorAll('button, [role=button], summary')).slice(0, 40).forEach(function (el) {
      attempt(el, function () { el.click(); });
    });
    [].slice.call(document.querySelectorAll('input[type=range], input[type=number]')).slice(0, 20).forEach(function (el) {
      ['min', 'max'].forEach(function (key) {
        var v = el.getAttribute(key);
        if (v !== null) attempt(el, function () { el.value = v; fire(el, 'input'); fire(el, 'change'); });
      });
    });
    [].slice.call(document.querySelectorAll('input[type=checkbox], input[type=radio]')).slice(0, 20).forEach(function (el) {
      attempt(el, function () { el.click(); });
    });
    [].slice.call(document.querySelectorAll('select')).slice(0, 10).forEach(function (el) {
      attempt(el, function () { el.selectedIndex = el.options.length - 1; fire(el, 'input'); fire(el, 'change'); });
    });
    R.info.interactions = count;
  }

  function finish(R) {
    errs.forEach(function (m) { add(R.errors, 'script-error', m, 10); });
    var text = JSON.stringify(R);
    var holder = document.createElement('script');
    holder.type = 'application/json';
    holder.id = REPORT_ID;
    holder.textContent = text.replace(/</g, '\\u003c');
    (document.body || document.documentElement).appendChild(holder);
    if (window.parent !== window) {
      try { window.parent.postMessage({ demystifyReport: text }, '*'); } catch (e) { /* not embedded */ }
    }
  }

  function start() {
    var R = { errors: [], warnings: [], info: {} };
    try {
      auditHtml(R);
      var pictures = [].slice.call(document.querySelectorAll('svg')).filter(function (svg) {
        return shown(svg) && !svg.closest('button, label, summary');
      });
      pictures.forEach(function (svg, index) { auditSvg(svg, R, index, pictures.length); });
    } catch (e) { add(R.errors, 'audit-failed', String(e)); }
    try { smoke(R); } catch (e) { errs.push('while pressing the controls: ' + e.message); }
    setTimeout(function () {
      var known = R.errors.some(function (e) { return e.rule === 'horizontal-overflow'; });
      try { if (!known) overflowCheck(R, 'after the controls were used'); } catch (e) { /* keep the report */ }
      finish(R);
    }, 400);
  }

  if (document.readyState === 'complete') setTimeout(start, 300);
  else window.addEventListener('load', function () { setTimeout(start, 300); });
})();
"""

EMBED_LISTENER = (
    "<script>window.addEventListener('message',function(e){var d=e.data||{};"
    "var text=d.demystifyReport||d.demystifyProbe;if(!text)return;"
    "var s=document.createElement('script');s.type='application/json';"
    "s.id=d.demystifyReport?'" + REPORT_ID + "':'" + PROBE_ID + "';"
    "s.textContent=text.replace(/</g,'\\\\u003c');document.body.appendChild(s);});</script>"
)


# --------------------------------------------------------------------------- checks without a browser


class _Scan(HTMLParser):
    """Finds external requests, files that the page depends on, ids, and references to ids."""

    URL_ATTRS = ("src", "href", "xlink:href", "poster", "data", "srcset")
    INLINE_SCHEMES = re.compile(r"(?i)^(data|blob|javascript|about|mailto|tel):")
    LINK_RELS_OK = ("canonical", "author", "license", "help", "alternate")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = set()
        self.external = []
        self.local_files = []
        self.fragment_refs = []  # (tag, id)
        self.url_refs = []  # ids used through url(#id)
        self.scripts = 0
        self.foreign_objects = 0
        self.in_style = False
        self.in_script = False
        self.network_calls = []
        self.template_text = []

    def handle_starttag(self, tag, attrs):
        values = dict((k, v or "") for k, v in attrs)
        if values.get("id"):
            self.ids.add(values["id"])
        if tag == "script":
            self.scripts += 1
            self.in_script = True
        elif tag == "style":
            self.in_style = True
        elif tag == "foreignobject":
            self.foreign_objects += 1
        for key in ("aria-label", "alt", "title", "placeholder"):
            if TEMPLATE_RE.search(values.get(key, "")):
                self.template_text.append(re.sub(r"\s+", " ", values[key]).strip()[:60])
        link_ok = tag == "link" and values.get("rel", "").lower() in self.LINK_RELS_OK
        for key in self.URL_ATTRS:
            value = values.get(key, "").strip()
            if not value or self.INLINE_SCHEMES.match(value):
                continue
            if value.startswith("#"):
                self.fragment_refs.append((tag, value[1:]))
            elif tag == "a" or link_ok:
                continue
            elif re.match(r"(?i)(https?:)?//", value):
                self.external.append("<%s %s=\"%s\">" % (tag, key, value[:80]))
            else:
                self.local_files.append("<%s %s=\"%s\">" % (tag, key, value.split()[0][:80]))
        for value in values.values():
            self._css(value)

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_script = False
        elif tag == "style":
            self.in_style = False

    def handle_data(self, data):
        if self.in_style:
            self._css(data)
            for match in re.finditer(r"@import\s+(?:url\()?['\"]?((?:https?:)?//[^'\")\s]+)", data):
                self.external.append("@import %s" % match.group(1)[:80])
        elif self.in_script:
            for match in re.finditer(
                r"(?:fetch|XMLHttpRequest|WebSocket|EventSource|importScripts|import)\s*\(?[^;\n]{0,40}?"
                r"['\"]((?:https?:|wss?:)?//[^'\"]+)['\"]", data):
                self.network_calls.append(match.group(1)[:80])
        elif TEMPLATE_RE.search(data):
            self.template_text.append(re.sub(r"\s+", " ", data).strip()[:60])

    def _css(self, text):
        for match in re.finditer(r"url\(\s*['\"]?#([^'\")\s]+)", text):
            self.url_refs.append(match.group(1))
        for match in re.finditer(r"url\(\s*['\"]?((?:https?:)?//[^'\")\s]+)", text):
            self.external.append("url(%s)" % match.group(1)[:80])


def static_checks(text: str, is_svg: bool) -> dict:
    errors, warnings = [], []
    if is_svg:
        try:
            ElementTree.fromstring(text.encode("utf-8"))
        except ElementTree.ParseError as exc:
            errors.append({
                "rule": "not-well-formed",
                "detail": "the SVG is not valid XML (%s): a browser shows an error page in place of the drawing. "
                          "Usual causes: a bare & or < in text, or a tag that is not closed" % exc,
            })
    scan = _Scan()
    scan.feed(text)
    scan.close()
    for item in scan.external[:8]:
        errors.append({"rule": "external-request",
                       "detail": "%s: the file must work offline, so put the content in the file" % item})
    for item in scan.local_files[:8]:
        errors.append({"rule": "needs-another-file",
                       "detail": "%s: the result must be one file, so put the content in the file" % item})
    for url in scan.network_calls[:4]:
        warnings.append({"rule": "network-call", "detail": "a script contacts %s" % url})
    for ref in sorted(set(scan.url_refs)):
        if ref not in scan.ids:
            errors.append({
                "rule": "missing-reference",
                "detail": "url(#%s) points at an element that does not exist "
                          "(an arrowhead, gradient, or clip path is missing)" % ref,
            })
    for tag, ref in scan.fragment_refs:
        if ref and ref not in scan.ids:
            item = {"rule": "missing-reference", "detail": "<%s> refers to #%s, which does not exist" % (tag, ref)}
            (warnings if tag == "a" else errors).append(item)
    if is_svg and scan.scripts:
        warnings.append({"rule": "svg-script",
                         "detail": "the SVG has a script: many viewers remove it, and a diagram does not need one"})
    if is_svg and scan.foreign_objects:
        warnings.append({"rule": "svg-foreign-object",
                         "detail": "foreignObject does not show in many viewers: use text elements"})
    if len(text.encode("utf-8")) > 2000000:
        warnings.append({"rule": "large-file", "detail": "the file is larger than 2 MB"})
    return {"errors": errors, "warnings": warnings, "template_text": scan.template_text}


def template_error(texts: list):
    """One error for all the sample text that is still in the result."""
    unique = []
    for text in texts:
        if text and text not in unique:
            unique.append(text)
    if not unique:
        return None
    shown = "; ".join('"%s"' % text for text in unique[:8])
    more = " and %d more" % (len(unique) - 8) if len(unique) > 8 else ""
    return {"rule": "template-text",
            "detail": "sample text from the template is still in the result (the word EDIT marks it): %s%s" % (shown, more)}


# --------------------------------------------------------------------------- rendering


def svg_size(text: str):
    """Natural size of an SVG in px, from width/height or from viewBox."""
    head = re.search(r"<svg\b[^>]*>", text, re.IGNORECASE | re.DOTALL)
    tag = head.group(0) if head else ""

    def attribute(name):
        match = re.search(r"\b%s\s*=\s*[\"']([^\"']+)[\"']" % name, tag)
        return match.group(1).strip() if match else ""

    def pixels(value):
        match = re.fullmatch(r"([0-9.]+)(px)?", value)
        return float(match.group(1)) if match else 0.0

    width, height = pixels(attribute("width")), pixels(attribute("height"))
    view = re.split(r"[\s,]+", attribute("viewBox"))
    if len(view) == 4:
        try:
            view_w, view_h = float(view[2]), float(view[3])
        except ValueError:
            view_w = view_h = 0.0
        if view_w > 0 and view_h > 0:
            if not width and not height:
                width, height = view_w, view_h
            elif not height:
                height = width * view_h / view_w
            elif not width:
                width = height * view_w / view_h
    if not width or not height:
        width, height = 1200.0, 675.0
    if width > SVG_MAX_WIDTH:
        width, height = float(SVG_MAX_WIDTH), height * SVG_MAX_WIDTH / width
    return int(round(width)), int(round(height))


def with_scripts(html: str, first: str, last: str) -> str:
    """Copy of a page with one script first in the head and one last in the body."""
    match = re.search(r"<head\b[^>]*>", html, re.IGNORECASE)
    if match:
        at = match.end()
    else:
        match = re.search(r"<html\b[^>]*>", html, re.IGNORECASE)
        if match:
            at = match.end()
        else:
            doctype = re.match(r"\s*<!doctype[^>]*>", html, re.IGNORECASE)
            at = doctype.end() if doctype else 0
    html = html[:at] + first + html[at:]
    at = html.lower().rfind("</body>")
    return html[:at] + last + html[at:] if at != -1 else html + last


def svg_wrapper(svg_text: str, width: int, audit: bool) -> str:
    body = re.sub(r"^\s*<\?xml[^>]*\?>", "", svg_text)
    body = re.sub(r"<!DOCTYPE[^>]*>", "", body, flags=re.IGNORECASE)
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">" + (ERROR_COLLECTOR if audit else "") +
        "<style>html,body{margin:0;background:#fff}#demystify-root{width:" + str(width) + "px}"
        "#demystify-root>svg{display:block;width:100%;height:auto}</style></head>"
        "<body><div id=\"demystify-root\">" + body + "</div>" +
        ("<script>" + AUDIT_JS + "</script>" if audit else "") + "</body></html>"
    )


def zoom_wrapper(svg_text: str, width: int, region, scale: float) -> str:
    """A page that shows one region of an SVG, enlarged. The region is in the units of the drawing."""
    x, y, w, h = region
    body = re.sub(r"^\s*<\?xml[^>]*\?>", "", svg_text)
    body = re.sub(r"<!DOCTYPE[^>]*>", "", body, flags=re.IGNORECASE)
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\"><style>html,body{margin:0;background:#fff}"
        "#frame{width:%dpx;height:%dpx;overflow:hidden}#inner{width:%dpx;margin-left:-%dpx;margin-top:-%dpx}"
        "#inner>svg{display:block;width:100%%;height:auto}</style></head><body><div id=\"frame\"><div id=\"inner\">%s"
        "</div></div></body></html>"
        % (int(w * scale), int(h * scale), int(width * scale), int(x * scale), int(y * scale), body)
    )


def frames_wrapper(file_url: str, offsets: list, width: int, height: int, listen: bool) -> str:
    """A page that shows another page in frames of an exact size, one frame for each scroll position.

    A frame gives the page a true viewport of that size, which the window of a headless browser
    does not: the window cannot be narrower than 500 px, and its height is not the viewport height.
    """
    cells = "".join(
        "<iframe src=\"%s#y%d\" style=\"display:block;flex:none;border:0;background:#fff;width:%dpx;height:%dpx\"></iframe>"
        % (file_url, offset, width, height)
        for offset in offsets
    )
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\"><style>html,body{margin:0;background:#6b7280}"
        "body{display:flex;gap:8px}</style></head><body>" + cells + (EMBED_LISTENER if listen else "") + "</body></html>"
    )


def slice_offsets(page_height: int, view_height: int, limit: int) -> list:
    """Scroll positions that show a page from the top down, one screen at a time."""
    count = max(1, min(limit, -(-page_height // view_height)))
    last = max(0, page_height - view_height)
    return [min(index * view_height, last) for index in range(count)]


class Browser:
    """Runs the browser headless, one short job at a time.

    The browser gets its own empty profile in the work folder, so it never
    touches the user's profile. A job ends when the browser exits or when its
    result is complete. Some browser versions do not exit by themselves after
    they write the result, so this class stops them.
    """

    TIMEOUT = 60  # seconds for one job

    def __init__(self, path: str, workdir: Path):
        self.path = path
        self.work = workdir
        self.profile = workdir / "profile"
        self.failure = ""
        self.jobs = 0

    def _command(self, width: int, height: int, extra: list, url: str) -> list:
        cmd = [
            self.path, "--headless=new", "--incognito", "--disable-gpu", "--no-first-run",
            "--no-default-browser-check", "--hide-scrollbars", "--mute-audio", "--disable-extensions",
            "--force-device-scale-factor=1", "--user-data-dir=%s" % self.profile,
            "--window-size=%d,%d" % (width, height),
        ]
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            cmd.append("--no-sandbox")
        # Extra browser options, for a machine where the browser needs them (for example --no-sandbox in a container).
        cmd += os.environ.get("DEMYSTIFY_BROWSER_ARGS", "").split()
        return cmd + extra + [url]

    def _job(self, cmd: list, done) -> str:
        """Run one job. Return what the browser printed."""
        self.jobs += 1
        self.failure = ""
        printed = self.work / ("stdout-%d.txt" % self.jobs)
        options = {"start_new_session": True} if os.name != "nt" else {}
        try:
            with open(str(printed), "wb") as out, open(os.devnull, "wb") as quiet:
                process = subprocess.Popen(cmd, stdout=out, stderr=quiet, **options)
                deadline = time.time() + self.TIMEOUT
                ready_at = None
                while process.poll() is None:
                    if done(printed):
                        ready_at = ready_at or time.time()
                        if time.time() - ready_at > 0.6:
                            break
                    if time.time() > deadline:
                        self.failure = "the browser did not finish in %d s" % self.TIMEOUT
                        break
                    time.sleep(0.15)
                self._stop(process)
        except OSError as exc:
            self.failure = "the browser did not start: %s" % exc
            return ""
        return printed.read_text(encoding="utf-8", errors="replace")

    @staticmethod
    def _stop(process) -> None:
        if process.poll() is not None:
            return
        for sig in (signal.SIGTERM, getattr(signal, "SIGKILL", signal.SIGTERM)):
            try:
                if os.name != "nt":
                    os.killpg(process.pid, sig)
                else:
                    process.terminate()
            except (OSError, ProcessLookupError):
                pass
            try:
                process.wait(5)
                return
            except subprocess.TimeoutExpired:
                continue

    def read(self, url: str, width: int, height: int, element_id: str = REPORT_ID):
        """Load the page and return the JSON that its script wrote into the element with this id."""
        pattern = re.compile(r"<script[^>]*id=\"%s\"[^>]*>(.*?)</script>" % re.escape(element_id), re.DOTALL)

        def done(printed: Path) -> bool:
            try:
                return bool(pattern.search(printed.read_text(encoding="utf-8", errors="replace")))
            except OSError:
                return False

        text = self._job(self._command(width, height, ["--virtual-time-budget=6000", "--dump-dom"], url), done)
        match = pattern.search(text)
        if not match:
            self.failure = self.failure or "no report came back"
            return None
        try:
            return json.loads(match.group(1))
        except ValueError:
            self.failure = "the report could not be read"
            return None

    def audit(self, url: str, width: int, height: int):
        return self.read(url, width, height, REPORT_ID)

    def screenshot(self, url: str, width: int, height: int, target: Path) -> bool:
        if target.exists():
            target.unlink()
        sizes = []

        def done(_printed: Path) -> bool:
            size = target.stat().st_size if target.exists() else 0
            sizes.append(size)
            return size > 0 and len(sizes) > 2 and sizes[-1] == sizes[-3]

        self._job(self._command(width, height, ["--virtual-time-budget=3000", "--screenshot=%s" % target], url), done)
        return target.exists() and target.stat().st_size > 0


def merge(total: dict, part: dict, prefix: str = "", hide: str = "") -> None:
    """Add findings to the report once. `prefix` marks findings that exist only at phone width."""
    for key in ("errors", "warnings"):
        for item in part.get(key, []):
            if hide and hide in item["detail"]:
                continue  # a file that the copy in the work folder could not load: reported as needs-another-file
            seen = any(e["rule"] == item["rule"] and e["detail"] in (item["detail"], prefix + item["detail"])
                       for e in total[key])
            if not seen:
                total[key].append({"rule": item["rule"], "detail": prefix + item["detail"]})


def look(path: Path, out: Path, mobile: bool, width: int, zooms=(), actions=(), prints=()) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    is_svg = path.suffix.lower() == ".svg" or text.lstrip()[:300].lower().startswith(("<svg", "<?xml"))
    report = {"file": str(path), "kind": "svg" if is_svg else "html", "rendered": False,
              "errors": [], "warnings": [], "screenshots": [], "info": {}}
    static = static_checks(text, is_svg)
    merge(report, static)
    leftovers = list(static["template_text"])

    browser_path = find_browser()
    if not browser_path:
        error = template_error(leftovers)
        if error:
            report["errors"].append(error)
        report["problem"] = (
            "No Chrome-family browser found (Chrome, Chromium, Edge, Brave), so nothing was rendered. "
            "Set DEMYSTIFY_BROWSER to the browser program if it is in another place.")
        return report

    report["browser"] = Path(browser_path).name
    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="demystify-look-"))
    try:
        browser = Browser(browser_path, work)
        if is_svg:
            svg_w, svg_h = svg_size(text)
            window = (max(svg_w, 500), max(svg_h, 300))
            audited = work / "audit.html"
            audited.write_text(svg_wrapper(text, svg_w, audit=True), encoding="utf-8")
            result = browser.audit(audited.as_uri(), window[0], window[1])
            if result is None:
                report["problem"] = "The browser did not return a layout report (%s)." % browser.failure
            else:
                merge(report, result, hide=work.as_uri())
                report["info"].update(result.get("info", {}))
                report["rendered"] = True
            # The screenshot shows the file itself, as a browser opens it. A file that is not valid XML
            # shows the error page of the browser here, which is what the user would see.
            shot = out / (path.stem + ".png")
            if browser.screenshot(path.resolve().as_uri(), window[0], window[1], shot):
                report["screenshots"].append(str(shot))
                report["rendered"] = True
            for index, region in enumerate(zooms, 1):
                x, y, w, h = region
                scale = max(1.0, min(3.0, 1600.0 / w))
                page = work / ("zoom-%d.html" % index)
                page.write_text(zoom_wrapper(text, svg_w, region, scale), encoding="utf-8")
                shot = out / ("%s.zoom-%d.png" % (path.stem, index))
                if browser.screenshot(page.as_uri(), max(500, int(w * scale)), max(120, int(h * scale)), shot):
                    report["screenshots"].append(str(shot))
            return report

        audited = work / "audit.html"
        audited.write_text(with_scripts(text, NO_MOTION + ERROR_COLLECTOR, "<script>" + AUDIT_JS + "</script>"),
                           encoding="utf-8")
        scrolling = work / "shot.html"
        scrolling.write_text(with_scripts(text, NO_MOTION, SCROLL_TO_HASH), encoding="utf-8")
        window = max(500, width)  # the window of a headless browser cannot be narrower than this

        def frames(name: str, offsets: list, frame_width: int, frame_height: int, target: Path, source=None) -> bool:
            """Screenshot a copy of the page in frames of an exact viewport size, one for each scroll position."""
            page = work / (name + ".html")
            page.write_text(frames_wrapper((source or scrolling).as_uri(), offsets, frame_width, frame_height,
                                           listen=False), encoding="utf-8")
            total = len(offsets) * frame_width + (len(offsets) - 1) * 8
            return browser.screenshot(page.as_uri(), max(500, total), frame_height, target)

        # Desktop: measure, then one screenshot for each screen of the page, top to bottom.
        wrapper = work / "desktop-audit.html"
        wrapper.write_text(frames_wrapper(audited.as_uri(), [0], width, DESKTOP_HEIGHT, listen=True), encoding="utf-8")
        result = browser.audit(wrapper.as_uri(), window, DESKTOP_HEIGHT)
        page_height = DESKTOP_HEIGHT
        content_height = int((result or {}).get("info", {}).get("content") or 0)
        if result is None:
            report["problem"] = "The browser did not return a layout report (%s)." % browser.failure
        else:
            merge(report, result, hide=work.as_uri())
            report["info"].update(result.get("info", {}))
            report["rendered"] = True
            page_height = int((result.get("info", {}).get("page") or [0, DESKTOP_HEIGHT])[1] or DESKTOP_HEIGHT)
            if not result.get("info", {}).get("controls"):
                report["warnings"].append({
                    "rule": "no-controls",
                    "detail": "the page has nothing to press or move: a page must react to the reader, or be a diagram"})
        offsets = slice_offsets(page_height, DESKTOP_HEIGHT, DESKTOP_MAX_SLICES)
        for index, offset in enumerate(offsets, 1):
            suffix = ".desktop.png" if len(offsets) == 1 else ".desktop-%d.png" % index
            shot = out / (path.stem + suffix)
            if frames("desktop-%d" % index, [offset], width, DESKTOP_HEIGHT, shot):
                report["screenshots"].append(str(shot))
                report["rendered"] = True
        not_shown = []
        if page_height > offsets[-1] + DESKTOP_HEIGHT:
            not_shown.append("the page is %d px high, and the desktop screenshots show the first %d px" % (
                page_height, offsets[-1] + DESKTOP_HEIGHT))

        def probe(name: str, action: str, expressions=()):
            """A copy of the page that runs the code. Returns the copy and what the code did."""
            page = work / (name + ".html")
            page.write_text(with_scripts(text, NO_MOTION, probe_script(action, expressions)), encoding="utf-8")
            holder = work / (name + "-read.html")
            holder.write_text(frames_wrapper(page.as_uri(), [0], width, DESKTOP_HEIGHT, listen=True), encoding="utf-8")
            return page, browser.read(holder.as_uri(), window, DESKTOP_HEIGHT, PROBE_ID)

        # The value of each expression that the caller gave, in the page as it loads.
        if prints:
            _page, values = probe("print", "", prints)
            for index, code in enumerate(prints, 1):
                item = (values or {}).get("values", [])[index - 1:index]
                entry = {"code": code}
                if not item:
                    entry["error"] = "the browser did not return a value (%s)" % (browser.failure or "no result")
                else:
                    entry.update(item[0])
                report.setdefault("values", []).append(entry)
                if "error" in entry:
                    report["errors"].append({"rule": "print-failed",
                                             "detail": "--print %d failed: %s" % (index, entry["error"])})

        # States that are not the state at the start: run the code that the caller gave, then take screenshots.
        for index, code in enumerate(actions, 1):
            page, state = probe("do-%d" % index, code)
            entry = {"code": code, "page": (state or {}).get("page"), "screenshots": []}
            if state is None:
                report["warnings"].append({"rule": "do-not-read", "detail": "--do %d: the browser did not report "
                                           "the result of the code (%s)" % (index, browser.failure or "no result")})
            elif state.get("error"):
                report["errors"].append({"rule": "do-failed", "detail": "--do %d failed, so its screenshot does not "
                                         "show the state that you want: %s" % (index, state["error"])})
            elif content_height and abs(int(state.get("content") or 0) - content_height) > 2:
                change = int(state.get("content") or 0) - content_height
                report["warnings"].append({
                    "rule": "page-jumps",
                    "detail": "after --do %d the page is %d px %s than at the start: give the area that changes "
                              "a fixed size" % (index, abs(change), "higher" if change > 0 else "lower")})
            shot = out / ("%s.do-%d.png" % (path.stem, index))
            if frames("do-%d-desktop" % index, [0], width, DESKTOP_HEIGHT, shot, page):
                entry["screenshots"].append(str(shot))
            if mobile:
                shot = out / ("%s.do-%d.mobile.png" % (path.stem, index))
                if frames("do-%d-phone" % index, [0], PHONE_WIDTH, PHONE_HEIGHT, shot, page):
                    entry["screenshots"].append(str(shot))
            report["screenshots"] += entry["screenshots"]
            report.setdefault("states", []).append(entry)

        if mobile:
            wrapper = work / "phone-audit.html"
            wrapper.write_text(frames_wrapper(audited.as_uri(), [0], PHONE_WIDTH, PHONE_HEIGHT, listen=True),
                               encoding="utf-8")
            phone = browser.audit(wrapper.as_uri(), 500, PHONE_HEIGHT)
            phone_height = PHONE_HEIGHT
            if phone is None:
                report["warnings"].append({"rule": "phone-not-checked", "detail": "the phone-width check did not run"})
            else:
                merge(report, phone, "at phone width: ", hide=work.as_uri())
                phone_height = int((phone.get("info", {}).get("page") or [0, PHONE_HEIGHT])[1] or PHONE_HEIGHT)
                report["info"]["phone_page"] = phone.get("info", {}).get("page")
            offsets = slice_offsets(phone_height, PHONE_HEIGHT, PHONE_MAX_SCREENS)
            strips = [offsets[i:i + PHONE_COLUMNS] for i in range(0, len(offsets), PHONE_COLUMNS)]
            for index, strip in enumerate(strips, 1):
                suffix = ".mobile.png" if len(strips) == 1 else ".mobile-%d.png" % index
                shot = out / (path.stem + suffix)
                if frames("phone-%d" % index, strip, PHONE_WIDTH, PHONE_HEIGHT, shot):
                    report["screenshots"].append(str(shot))
            report["info"]["phone_screens"] = len(offsets)
            if phone_height > offsets[-1] + PHONE_HEIGHT:
                not_shown.append("at phone width the page is %d px high, and the screenshots show the first %d px" % (
                    phone_height, offsets[-1] + PHONE_HEIGHT))
        if not_shown:
            report["info"]["not_shown"] = "; ".join(not_shown)
    finally:
        shutil.rmtree(str(work), ignore_errors=True)
        leftovers += report["info"].pop("templateText", None) or []
        error = template_error(leftovers)
        if error:
            report["errors"].append(error)
    return report


def render(report: dict) -> str:
    errors, warnings = report["errors"], report["warnings"]
    if not report["rendered"]:
        status = "NOT RENDERED"
    else:
        status = "%d error%s, %d warning%s" % (
            len(errors), "" if len(errors) == 1 else "s", len(warnings), "" if len(warnings) == 1 else "s")
    lines = ["look: %s — %s" % (status, report["file"])]
    if report.get("browser"):
        lines.append("  rendered with %s" % report["browser"])
    if report.get("problem"):
        lines.append("  " + report["problem"])
    for item in errors:
        lines.append("  ERROR %s: %s" % (item["rule"], item["detail"]))
    for item in warnings:
        lines.append("  warn  %s: %s" % (item["rule"], item["detail"]))
    info = report.get("info", {})
    if info.get("page") and report["kind"] == "html":
        lines.append("  page %s x %s px · %s controls · the check pressed or moved them %s times" % (
            info["page"][0], info["page"][1], info.get("controls", 0), info.get("interactions", 0)))
    if info.get("not_shown"):
        lines.append("  " + info["not_shown"])
    for index, entry in enumerate(report.get("values", []), 1):
        if "value" in entry:
            lines.append("  --print %d: %s" % (index, entry["value"]))
    for index, entry in enumerate(report.get("states", []), 1):
        if entry.get("page"):
            lines.append("  --do %d: the page is %s x %s px in this state" % (index, entry["page"][0], entry["page"][1]))
    for shot in report["screenshots"]:
        lines.append("  screenshot: %s" % shot)
    if report["screenshots"]:
        lines.append("  Now look at the screenshot%s. The measurements above do not find every fault."
                     % ("" if len(report["screenshots"]) == 1 else "s"))
        if info.get("phone_screens", 0) > 1:
            lines.append("  A phone screenshot shows the page at %d px wide, as screens side by side. "
                         "The top of the page is at the left." % PHONE_WIDTH)
        if report["kind"] == "html" and not report.get("states"):
            lines.append("  The screenshots show the page as it loads. To see another state, add --do with JavaScript, for example:")
            lines.append("    --do \"document.querySelector('button').click()\"")
    elif not report["rendered"]:
        lines.append("  Say in your report that nobody looked at the rendered result.")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Render an SVG or HTML file, save screenshots, and measure the layout.")
    parser.add_argument("file", help="an .svg or .html file")
    parser.add_argument("--out", help="folder for the screenshots (default: review/ next to the file)")
    parser.add_argument("--mobile", action="store_true", help="HTML only: also render at phone width")
    parser.add_argument("--width", type=int, default=DESKTOP_WIDTH,
                        help="HTML only: width of the window in px (default %d, smallest 320)" % DESKTOP_WIDTH)
    parser.add_argument("--do", action="append", default=[], metavar="JS",
                        help="HTML only: run this JavaScript in the page, then save one more screenshot. "
                             "Repeat it for more states")
    parser.add_argument("--print", action="append", default=[], metavar="JS", dest="prints",
                        help="HTML only: print the value of this JavaScript expression in the page. "
                             "Repeat it for more values")
    parser.add_argument("--zoom", action="append", default=[], metavar="X,Y,W,H",
                        help="SVG only: also save an enlarged picture of this region. Repeat it for more regions")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)

    path = Path(args.file)
    if not path.is_file():
        print("look: cannot read %s" % path, file=sys.stderr)
        return 2
    zooms = []
    for value in args.zoom:
        try:
            region = [float(part) for part in value.split(",")]
        except ValueError:
            region = []
        if len(region) != 4 or region[2] <= 0 or region[3] <= 0:
            print("look: --zoom needs four numbers X,Y,W,H in the units of the drawing, for example 0,0,800,400",
                  file=sys.stderr)
            return 2
        zooms.append(region)
    out = Path(args.out) if args.out else path.resolve().parent / "review"
    report = look(path, out, args.mobile, max(320, args.width), zooms, args.do, args.prints)
    print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else render(report))
    if not report["rendered"]:
        return 2
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
