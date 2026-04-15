from pymongo import MongoClient
from urllib.parse import quote_plus
from dotenv import load_dotenv
import os
import logging

load_dotenv()

logger = logging.getLogger(__name__)

mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
db_name = os.getenv("MONGO_DB_NAME") or os.getenv("MONGODB_DB_NAME") or "assessment_db"

client = None

if mongo_uri:
	try:
		client = MongoClient(mongo_uri)
		client.admin.command("ping")
	except Exception as exc:
		logger.error(f"Failed to connect to MongoDB: {exc}")
		client = None

if client:
	db = client[db_name]
	questions_collection = db["writing_questions"]
	users_collection = db["users"]
else:
	questions_collection = None
	users_collection = None