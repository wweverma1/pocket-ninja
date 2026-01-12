from app.product.worker import start_product_sync_thread
from app.leaderboard.routes import leaderboard_endpoints
from app.feedback.routes import feedback_endpoints
from app.product.routes import product_endpoints
from app.user.routes import user_endpoints
from app.auth.routes import auth_endpoints
from app.home.routes import home_endpoints
from pymongo.server_api import ServerApi
from pymongo import MongoClient
import os

from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024

allowed_origins = [
    "https://pocket-ninja.netlify.app",
    "http://localhost:5173",
]

CORS(app, resources={r"/*": {
    "origins": allowed_origins,
    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    "allow_headers": ["Content-Type", "Authorization"]
}})


db = None

MONGO_URI = os.getenv("MONGO_DB_URI")
DB_NAME = os.getenv("DB_NAME")

try:
    if not MONGO_URI:
        print("Warning: MONGO_DB_URI not found.")
    else:
        client = MongoClient(MONGO_URI, server_api=ServerApi('1'))
        client.admin.command('ping')

        db = client[DB_NAME]
        print("MongoDB connection established successfully.")
except Exception as e:
    print(f"Error connecting to MongoDB: {e}")


app.register_blueprint(home_endpoints)
app.register_blueprint(auth_endpoints)
app.register_blueprint(user_endpoints)
app.register_blueprint(product_endpoints)
app.register_blueprint(feedback_endpoints)
app.register_blueprint(leaderboard_endpoints)


try:
    if db is not None:
        start_product_sync_thread(app)
except Exception as e:
    print(f"Failed to start background worker: {e}")
