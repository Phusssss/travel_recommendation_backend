import os
import requests
import mysql.connector
from cachetools import TTLCache
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from requests.exceptions import HTTPError
import structlog

# Cấu hình structlog
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

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
        logger.error("Database connection failed", error=str(e))
        raise

def get_city_id(city: str) -> int:
    """Lấy city_id từ bảng cities dựa trên tên thành phố."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM cities WHERE name = %s", (city,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        if result:
            logger.info("Fetched city_id", city=city, city_id=result[0])
            return result[0]
        logger.error("City not found", city=city)
        raise ValueError(f"City {city} not found in database")
    except Exception as e:
        logger.error("Error fetching city_id", error=str(e))
        raise

def get_coordinates(location: str, city: str) -> list:
    """Lấy tọa độ (longitude, latitude) của một địa điểm từ database hoặc ORS Geocoding."""
    city_id = get_city_id(city)
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT latitude, longitude FROM destinations WHERE name = %s AND city_id = %s",
            (location, city_id)
        )
        result = cursor.fetchone()
        if result and result[0] is not None and result[1] is not None:
            lat, lon = result[0], result[1]
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                cursor.close()
                conn.close()
                return [lon, lat]
        cursor.close()
        conn.close()
    except Exception as e:
        logger.error("Error querying coordinates", error=str(e))

    # Gọi ORS Geocoding nếu không tìm thấy trong database
    coords = get_ors_coordinates(location, city)
    if coords:
        lat, lon = coords
        # Lưu tọa độ vào database
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE destinations SET latitude = %s, longitude = %s, geocoded_at = NOW() "
                "WHERE name = %s AND city_id = %s",
                (lat, lon, location, city_id)
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            logger.error("Error saving coordinates", error=str(e))
        return [lon, lat]
    return None

def get_ors_coordinates(location: str, city: str, country: str = "Vietnam") -> tuple:
    """Lấy tọa độ từ OpenRouteService Geocoding API."""
    api_key = os.getenv("ORS_API_KEY")
    if not api_key:
        logger.error("ORS_API_KEY not set")
        return None
    url = "https://api.openrouteservice.org/geocode/autocomplete"
    params = {
        "api_key": api_key,
        "text": f"{location}, {city}, {country}",
        "boundary.country": "VN"
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if data["features"]:
            coords = data["features"][0]["geometry"]["coordinates"]
            return coords[1], coords[0]  # latitude, longitude
        logger.warning("No coordinates found", location=location)
        return None
    except Exception as e:
        logger.error("Error fetching coordinates", location=location, error=str(e))
        return None

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    retry=retry_if_exception_type(HTTPError),
    reraise=True
)
def get_travel_time(start_location: str, end_location: str, city: str) -> dict:
    """Lấy thời gian di chuyển giữa hai địa điểm, ưu tiên cache và database."""
    city_id = get_city_id(city)
    cache_key = f"{city_id}:{start_location}:{end_location}"
    
    # Kiểm tra cache
    if cache_key in travel_time_cache:
        logger.info("Cache hit for travel time", cache_key=cache_key)
        return travel_time_cache[cache_key]

    # Kiểm tra database
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT duration, updated_at FROM travel_times WHERE city_id = %s AND start_location = %s AND end_location = %s",
            (city_id, start_location, end_location)
        )
        result = cursor.fetchone()
        if result and result[1]:  # Kiểm tra thời gian cập nhật
            duration, updated_at = result
            travel_time_cache[cache_key] = {"duration": duration}
            logger.info("Database hit for travel time", cache_key=cache_key)
            cursor.close()
            conn.close()
            return {"duration": duration}
        cursor.close()
        conn.close()
    except Exception as e:
        logger.error("Error querying travel_times", error=str(e))

    # Kiểm tra tọa độ
    start_coords = get_coordinates(start_location, city)
    end_coords = get_coordinates(end_location, city)
    if not start_coords or not end_coords:
        logger.error("Invalid coordinates", start_location=start_location, end_location=end_location)
        return {"duration": "N/A"}

    # Kiểm tra ORS_API_KEY
    api_key = os.getenv("ORS_API_KEY")
    if not api_key:
        logger.error("ORS_API_KEY not set")
        return {"error": "Missing ORS_API_KEY"}

    # Gọi API OpenRouteService
    headers = {"Authorization": api_key}
    body = {"coordinates": [start_coords, end_coords]}
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
                "INSERT INTO travel_times (city_id, start_location, end_location, duration, updated_at) "
                "VALUES (%s, %s, %s, %s, NOW()) "
                "ON DUPLICATE KEY UPDATE duration = %s, updated_at = NOW()",
                (city_id, start_location, end_location, result["duration"], result["duration"])
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            logger.error("Error saving to travel_times", error=str(e))

        travel_time_cache[cache_key] = result
        return result
    except HTTPError as e:
        if response.status_code in (429, 404):
            logger.error("HTTP error in get_travel_time", error=str(e), status_code=response.status_code)
            if response.status_code == 429:
                raise
            return {"duration": "N/A"}
        return {"error": f"Cannot calculate travel time: {e}"}
    except Exception as e:
        logger.error("Error in get_travel_time", error=str(e))
        return {"error": f"Cannot calculate travel time: {e}"}

def get_current_weather(city: str) -> dict:
    """Lấy thông tin thời tiết hiện tại cho một thành phố."""
    api_key = os.getenv("WEATHER_API_KEY")
    if not api_key:
        logger.error("WEATHER_API_KEY not set")
        return {"error": "Missing WEATHER_API_KEY"}
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city},VN&appid={api_key}&units=metric"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return {
            "description": data["weather"][0]["description"],
            "temperature": data["main"]["temp"]
        }
    except Exception as e:
        logger.error("Error in get_current_weather", error=str(e), city=city)
        return {"error": f"Cannot get weather: {e}"}
    
