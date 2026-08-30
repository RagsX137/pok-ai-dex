from pokedex.app import app
from pokedex.config import settings

if __name__ == "__main__":
    import os
    app.run(debug=os.getenv("FLASK_DEBUG") == "1", port=settings.port)
