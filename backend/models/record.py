from pydantic import BaseModel


class Turn(BaseModel):
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
