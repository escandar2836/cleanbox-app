from cleanbox import create_app, init_db
import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

app = create_app()

if __name__ == "__main__":
    # Initialize DB in development environment
    init_db(app)

    # Read port setting from environment variable (default: 5001)
    port = int(os.environ.get("FLASK_PORT", 5001))

    # Run Flask server
    app.run(debug=True, host="0.0.0.0", port=port)
