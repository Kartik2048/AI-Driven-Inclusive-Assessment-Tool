from pymongo import MongoClient

MONGO_URI = "mongodb://localhost:27017/"
client = MongoClient('mongodb+srv://kartikjuneja2626:mongodbuser@cluster0.nwu7f5x.mongodb.net/')
db = client["assessment_db"]
questions_collection = db["writing_questions"]
users_collection = db["users"]