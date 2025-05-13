# app/main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.routes import router
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Travel Recommendation System")

# Cấu hình CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Đăng ký các route
app.include_router(router)

# Mount thư mục static

@app.get("/")
def read_root():
    return {"message": "Welcome to the Travel Recommendation API!"}