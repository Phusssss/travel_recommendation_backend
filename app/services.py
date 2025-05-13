
import os
import requests
import mysql.connector
from cachetools import TTLCache
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from requests.exceptions import HTTPError
import logging

logger = logging.getLogger(__name__)

# Bộ nhớ đệm với thời gian sống 1 giờ, tối đa 1000 mục
travel_time_cache = TTLCache(maxsize=1000, ttl=3600)

def get_db_connection():
    """Kết nối đến cơ sở dữ liệu MySQL."""
    try:
        conn = mysql.connector.connect(
            host=os.getenv("DB_HOST", "db"),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME", "travel_recommendation")
        )
        logger.info("Database connection established")
        return conn
    except mysql.connector.Error as e:
        logger.error(f"Database connection failed: {e}")
        raise

def get_coordinates(location: str) -> list:
    """Lấy tọa độ (longitude, latitude) của một địa điểm từ database."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT latitude, longitude FROM destinations WHERE name = %s AND city = %s",
            (location, "Da Lat")
        )
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        if result:
            return [result[1], result[0]]  # [longitude, latitude]
        logger.warning(f"No coordinates found for {location}")
        return [0, 0]
    except Exception as e:
        logger.error(f"Error in get_coordinates: {e}")
        return [0, 0]

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    retry=retry_if_exception_type(HTTPError),
    reraise=True
)
def get_travel_time(start_location: str, end_location: str) -> dict:
    """Lấy thời gian di chuyển giữa hai địa điểm, ưu tiên cache và database."""
    cache_key = f"{start_location}:{end_location}"
    
    # Kiểm tra cache
    if cache_key in travel_time_cache:
        logger.info(f"Cache hit for travel time: {cache_key}")
        return travel_time_cache[cache_key]

    # Kiểm tra database
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT duration FROM travel_times WHERE city = %s AND start_location = %s AND end_location = %s",
            ("Da Lat", start_location, end_location)
        )
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        if result:
            travel_time_cache[cache_key] = {"duration": result[0]}
            logger.info(f"Database hit for travel time: {cache_key}")
            return {"duration": result[0]}
    except Exception as e:
        logger.error(f"Error querying travel_times: {e}")

    # Kiểm tra ORS_API_KEY
    api_key = os.getenv("ORS_API_KEY")
    if not api_key:
        logger.error("ORS_API_KEY not set")
        return {"error": "Missing ORS_API_KEY"}

    # Gọi API OpenRouteService
    headers = {"Authorization": api_key}
    body = {
        "coordinates": [
            get_coordinates(start_location),
            get_coordinates(end_location)
        ]
    }
    try:
        response = requests.post(
            "https://api.openrouteservice.org/v2/directions/driving-car/geojson",
            json=body,
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()
        duration = data["features"][0]["properties"]["summary"]["duration"]
        result = {"duration": f"{duration / 60:.2f} mins"}

        # Lưu vào database
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO travel_times (city, start_location, end_location, duration) VALUES (%s, %s, %s, %s)",
                ("Da Lat", start_location, end_location, result["duration"])
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            logger.error(f"Error saving to travel_times: {e}")

        travel_time_cache[cache_key] = result
        return result
    except HTTPError as e:
        if response.status_code in (429, 404):
            logger.error(f"HTTP error in get_travel_time: {e}")
            if response.status_code == 429:
                raise
            return {"duration": "N/A"}
        return {"error": f"Cannot calculate travel time: {e}"}
    except Exception as e:
        logger.error(f"Error in get_travel_time: {e}")
        return {"error": f"Cannot calculate travel time: {e}"}

def get_current_weather(location: str) -> dict:
    """Lấy thông tin thời tiết hiện tại cho một địa điểm."""
    api_key = os.getenv("WEATHER_API_KEY")
    if not api_key:
        logger.error("WEATHER_API_KEY not set")
        return {"error": "Missing WEATHER_API_KEY"}
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={location},VN&appid={api_key}&units=metric"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return {"description": data["weather"][0]["description"]}
    except Exception as e:
        logger.error(f"Error in get_current_weather: {e}")
        return {"error": f"Cannot get weather: {e}"}
