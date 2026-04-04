from pymongo import MongoClient
from dotenv import load_dotenv
import os
import logging

load_dotenv()

logger = logging.getLogger(__name__)

# Get MongoDB URI from environment variable
MONGO_URI = os.getenv('MONGO_URI')

if not MONGO_URI:
    logger.warning("MONGO_URI not found in environment variables. Please add it to .env file")
    # Fallback for development (should be removed in production)
    MONGO_URI = 'mongodb://localhost:27017/'

try:
    client = MongoClient(MONGO_URI)
    # Verify connection
    client.admin.command('ping')
    logger.info("Connected to MongoDB successfully")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {str(e)}")
    client = None

if client:
    db = client["assessment_db"]
    questions_collection = db["writing_questions"]
    users_collection = db["users"]
else:
    questions_collection = None
    users_collection = None

