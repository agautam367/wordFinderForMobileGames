import os
from collections import Counter
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pymongo import AsyncMongoClient

MONGODB_URI = os.getenv("MONGODB_URI")        # ← fixed name
DB_NAME     = os.getenv("MONGODB_DB", "english_dictionary")

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not MONGODB_URI:
        raise ValueError("MONGODB_URI environment variable not set!")
    app.mongodb_client = AsyncMongoClient(MONGODB_URI)
    app.mongodb        = app.mongodb_client[DB_NAME]
    yield
    app.mongodb_client.close()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://agautam367.github.io",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

class WordSearchRequest(BaseModel):
    letters:    str           = Field(..., min_length=1, max_length=20)
    length:     Optional[int] = Field(None, ge=1, le=20)
    min_length: Optional[int] = Field(None, ge=1, le=20)

class WordSearchResponse(BaseModel):
    letters:    str
    length:     Optional[int]
    min_length: Optional[int]
    total:      int
    words:      list[str]

async def find_words(
    mongodb,
    letters:    str,
    length:     Optional[int] = None,
    min_length: Optional[int] = None,
) -> list[str]:
    available = Counter(letters.lower())
    valid     = []
    query     = {}

    if length:
        query["$expr"] = {"$eq": [{"$strLenCP": "$word"}, length]}
    elif min_length:
        query["$expr"] = {"$gte": [{"$strLenCP": "$word"}, min_length]}

    async for doc in mongodb.dictionary.find(query, {"word": 1, "_id": 0}):
        word       = doc["word"]
        word_count = Counter(word)
        if all(word_count[c] <= available[c] for c in word_count):
            valid.append(word)

    return sorted(valid, key=lambda w: (-len(w), w))

@app.get("/")
async def root():
    return {"status": "ok", "service": "word-finder"}

@app.post("/api/words", response_model=WordSearchResponse)
async def search_words_post(payload: WordSearchRequest, request: __import__('fastapi').Request):
    if not payload.letters.isalpha():
        raise HTTPException(status_code=422, detail="Letters must be alphabetic only")

    words = await find_words(
        request.app.mongodb,
        letters    = payload.letters,
        length     = payload.length,
        min_length = payload.min_length,
    )
    return WordSearchResponse(
        letters    = payload.letters.lower(),
        length     = payload.length,
        min_length = payload.min_length,
        total      = len(words),
        words      = words,
    )

@app.get("/api/words", response_model=WordSearchResponse)
async def search_words_get(
    request:    __import__('fastapi').Request,
    letters:    str           = Query(..., min_length=1, max_length=20),
    length:     Optional[int] = Query(None, ge=1, le=20),
    min_length: Optional[int] = Query(None, ge=1, le=20),
):
    if not letters.isalpha():
        raise HTTPException(status_code=422, detail="Letters must be alphabetic only")

    words = await find_words(
        request.app.mongodb,
        letters    = letters,
        length     = length,
        min_length = min_length,
    )
    return WordSearchResponse(
        letters    = letters.lower(),
        length     = length,
        min_length = min_length,
        total      = len(words),
        words      = words,
    )
