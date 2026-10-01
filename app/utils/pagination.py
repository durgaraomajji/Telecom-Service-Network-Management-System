from pydantic import BaseModel, Field
class PageParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
def paginate_query(query, page: int = 1, page_size: int = 20):
    return query.offset((page - 1) * page_size).limit(page_size)
