"""Request bodies. FastAPI checks them and returns 400 if a field is missing or has the wrong type."""

from pydantic import BaseModel


class Turn(BaseModel):
    # One earlier question and its answer, sent back for follow-up questions.
    question: str
    answer: str


class Question(BaseModel):
    question: str
    category: str = ""
    history: list[Turn] = []


class DocumentText(BaseModel):
    text: str


class Category(BaseModel):
    category: str
