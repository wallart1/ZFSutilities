"""
MkDocs hook: reads the project VERSION file and injects it into
config.extra.version so the Material theme can display it.
"""
import os


def on_config(config, **kwargs):
    """Read ../VERSION (relative to mkdocs.yml) and set extra.version."""
    mkdocs_dir = os.path.dirname(config.config_file_path)
    version_path = os.path.join(mkdocs_dir, '..', 'VERSION')
    try:
        with open(version_path) as f:
            version = f.read().strip()
        if version:
            config.extra['version'] = version
    except OSError:
        pass
    return config
