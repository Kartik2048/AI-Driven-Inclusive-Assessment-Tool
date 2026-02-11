from pymongo import MongoClient

MONGO_URI = "<MONGODB URI>" //enter your uri
client = MongoClient('<MONGODB CLIENT PERSONAL CODE>') #enter your code
db = client["assessment_db"]
questions_collection = db["writing_questions"]

users_collection = db["users"]

