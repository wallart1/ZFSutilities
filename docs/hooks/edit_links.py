"""
MkDocs hook: sets page.edit_url to an openmd:// URI so the pencil icon
on each page opens the source .md file in the desktop default app (MarkText).
"""
import os
import urllib.parse


def on_page_context(context, **kwargs):
    page = kwargs['page']
    config = kwargs['config']
    docs_dir = config['docs_dir']
    file_path = os.path.join(docs_dir, page.file.src_path)
    encoded = urllib.parse.quote(file_path, safe='/:@()')
    page.edit_url = f"openmd://{encoded}"
    return context
