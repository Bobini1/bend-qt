"""Public plugin discovery before QtWebView's fatal missing-backend path."""
from pathlib import Path


def before_call(g, method):
    if method['function']['constructor'] and 'QWebView' in [method['class']] + g.all_bases(method['class']):
        return ['if (!webview_backend_ready(r)) return true;']
    return []


def cpp(g):
    if 'QWebView' not in g.ids:
        return ''
    return (Path(__file__).parent / 'templates/webview_runtime.cpp').read_text()
