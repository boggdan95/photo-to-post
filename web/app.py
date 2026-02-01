"""Flask web app for reviewing, approving, and scheduling posts."""

# TODO: Phase 3
# - Review posts screen with photo grid
# - Caption editing
# - Photo reordering
# - Calendar view
# - Settings editor

from flask import Flask

app = Flask(__name__)


@app.route("/")
def index():
    return "<h1>photo-to-post</h1><p>Web interface coming in Phase 3.</p>"


if __name__ == "__main__":
    app.run(debug=True, port=5000)
