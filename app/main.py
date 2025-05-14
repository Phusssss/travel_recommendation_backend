from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from app.routes import router
from app.services import get_db_connection
from fastapi.middleware.cors import CORSMiddleware
import structlog
import mysql.connector

logger = structlog.get_logger()

app = FastAPI(title="Travel Recommendation System")

# Cấu hình CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount thư mục static

# Đăng ký các route
app.include_router(router)

@app.get("/")
def read_root():
    return {"message": "Welcome to the Travel Recommendation API!"}

@app.get("/health")
async def health_check():
    """Kiểm tra trạng thái hệ thống."""
    try:
        conn = get_db_connection()
        conn.close()
        logger.info("Health check passed")
        return {"status": "healthy", "database": "connected"}
    except mysql.connector.Error as e:
        logger.error("Health check failed", error=str(e))
        return {"status": "unhealthy", "database": "disconnected"}