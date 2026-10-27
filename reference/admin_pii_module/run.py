from dotenv import load_dotenv
load_dotenv()
from clinical_compass.api import create_app

app = create_app()

if __name__ == "__main__":
    # Development-only server. Deploy with a production WSGI server and HTTPS.
    app.run(host="127.0.0.1", port=5000, debug=False)
