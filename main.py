import os
from collections import Counter
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pymongo import AsyncMongoClient

MONGODB_URI = os.getenv("MONGODB_URI_ALPHA")
DB_NAME     = os.getenv("MONGODB_DB", "english_dictionary")

# ── Lifespan ────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.mongodb_client = AsyncMongoClient(MONGODB_URI)
    app.mongodb        = app.mongodb_client[DB_NAME]
    yield
    app.mongodb_client.close()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request / Response models ─────────────────────────────
class WordSearchRequest(BaseModel):
    letters:    str = Field(..., min_length=1, max_length=20,
                            description="Available letters e.g. 'tllief'")
    length:     int | None = Field(None, ge=1, le=20,
                            description="Exact word length (optional)")
    min_length: int | None = Field(None, ge=1, le=20,
                            description="Minimum word length (optional)")

class WordSearchResponse(BaseModel):
    letters:    str
    length:     int | None
    min_length: int | None
    total:      int
    words:      list[str]

# ── Core search logic ─────────────────────────────────────
async def find_words(
    mongodb,
    letters:    str,
    length:     int | None = None,
    min_length: int | None = None,
) -> list[str]:

    available = Counter(letters.lower())
    valid      = []

    # Build MongoDB query to pre-filter by length (faster)
    query = {}
    if length:
        query["$expr"] = {"$eq": [{"$strLenCP": "$word"}, length]}
    elif min_length:
        query["$expr"] = {"$gte": [{"$strLenCP": "$word"}, min_length]}

    async for doc in mongodb.dictionary.find(query, {"word": 1, "_id": 0}):
        word       = doc["word"]
        word_count = Counter(word)
        if all(word_count[c] <= available[c] for c in word_count):
            valid.append(word)

    return sorted(valid, key=lambda w: (-len(w), w))   # longest first, then alpha

# ── Endpoints ─────────────────────────────────────────────
@app.get("/")
async def root():
    return {"status": "ok", "service": "word-finder"}

@app.post("/api/words", response_model=WordSearchResponse)
async def search_words_post(payload: WordSearchRequest):
    """POST — search with JSON body"""
    # Validate letters are alpha only
    if not payload.letters.isalpha():
        raise HTTPException(
            status_code=422,
            detail="Letters must contain only alphabetic characters"
        )

    words = await find_words(
        app.mongodb,
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
    letters:    str       = Query(..., min_length=1, max_length=20),
    length:     int | None = Query(None, ge=1, le=20),
    min_length: int | None = Query(None, ge=1, le=20),
):
    """GET — search with query params e.g. /api/words?letters=tllief&length=4"""
    if not letters.isalpha():
        raise HTTPException(
            status_code=422,
            detail="Letters must contain only alphabetic characters"
        )

    words = await find_words(
        app.mongodb,
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