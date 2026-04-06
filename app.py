import os

from flask import Flask


def create_app() -> Flask:
    app = Flask(__name__)

    @app.route("/", methods=["GET"])
    def root() -> str:
        return "App is running"

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
