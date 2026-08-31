"""Pages blueprint: HTML pages and static-asset routes."""
from flask import Blueprint, render_template_string, send_from_directory

from pokedex.config import settings

pages_bp = Blueprint("pages", __name__)

_IMAGES_DIR   = settings.images_dir
_FRONTEND_DIR = settings.frontend_dir
_COVEO_ORG    = settings.coveo_org


@pages_bp.route("/")
def index():
    html = (_FRONTEND_DIR / "classic" / "index.html").read_text()
    return render_template_string(html, COVEO_ORGANIZATION_ID=_COVEO_ORG)


@pages_bp.route("/dashboard")
def dashboard():
    html = (_FRONTEND_DIR / "dashboard.html").read_text()
    return render_template_string(html, COVEO_ORGANIZATION_ID=_COVEO_ORG)


@pages_bp.route("/readme")
def readme():
    return send_from_directory(_FRONTEND_DIR, "readme.html")


@pages_bp.route("/frontend/<path:filename>")
def frontend_static(filename):
    return send_from_directory(_FRONTEND_DIR, filename)


@pages_bp.route("/images/<filename>")
def serve_image(filename):
    return send_from_directory(_IMAGES_DIR, filename)
