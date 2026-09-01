"""Flask application factory."""
from flask import Flask
from flask_cors import CORS

from pokedex import pokemon_names
from pokedex.config import settings
from pokedex.routes.coach_api import coach_bp
from pokedex.routes.coveo_api import coveo_bp
from pokedex.routes.llm_api import llm_bp
from pokedex.routes.pages import pages_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024  # 64 KB — ample for any real question
    # Read the name corpus at startup rather than on the first request. The
    # accessors in pokemon_names load on demand anyway, so this is a latency
    # choice, not a correctness one — it used to be a module-scope call in
    # coveo_api.py, where import order silently decided whether name
    # resolution worked at all.
    pokemon_names.init(settings.repo_root)
    # Scope CORS to this app's own origins. Reflecting any Origin let *any* website
    # read /api/coveo-token — i.e. the live Coveo API key — from a visitor's browser.
    CORS(app, origins=[
        f"http://127.0.0.1:{settings.port}",
        f"http://localhost:{settings.port}",
    ])
    app.register_blueprint(pages_bp)
    app.register_blueprint(coach_bp, url_prefix="/api")
    app.register_blueprint(coveo_bp, url_prefix="/api")
    app.register_blueprint(llm_bp, url_prefix="/api")
    return app


app = create_app()
