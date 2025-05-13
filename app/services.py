import json
import requests
import mysql.connector
from typing import Dict, Any, List
from mysql.connector import Error
import os

# OpenWeatherMap API Key
OPENWEATHER_API_KEY = "f45d404e8a927b961993a0cd9a641ce5"

# OpenRouteService API Key
ORS_API_KEY = os.getenv("ORS_API_KEY")

def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host=os.getenv("MYSQL_HOST", "localhost"),
            user=os.getenv("MYSQL_USER", "root"),
            password=os.getenv("MYSQL_PASSWORD", "your_password"),
            database=os.getenv("MYSQL_DATABASE", "travel_recommendation")
        )
        return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

def get_current_weather(city: str) -> Dict[str, Any]:
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError:
        return {"error": "City not found or invalid request"}
    except requests.exceptions.RequestException:
        return {"error": "Network error or API unavailable"}

def get_weather_forecast(city: str, days: int = 5) -> Dict[str, Any]:
    if days > 5:
        return {"error": "Forecast limited to 5 days"}
    url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={OPENWEATHER_API_KEY}&units=metric"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        daily_forecast = [
            item for item in data["list"]
            if "12:00:00" in item["dt_txt"]
        ][:days]
        return {
            "city": data["city"],
            "forecast": daily_forecast
        }
    except requests.exceptions.HTTPError:
        return {"error": "City not found or invalid request"}
    except requests.exceptions.RequestException:
        return {"error": "Network error or API unavailable"}

def get_weather_by_coordinates(lat: float, lon: float) -> Dict[str, Any]:
    url = f"http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError:
        return {"error": "Invalid coordinates or request"}
    except requests.exceptions.RequestException:
        return {"error": "Network error or API unavailable"}
def save_user_preferences(user_id: str, preferences: Dict[str, Any]) -> Dict[str, Any]:
    connection = get_db_connection()
    if not connection:
        return {"error": "Database connection failed"}
    
    try:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO users (user_id, preferences) VALUES (%s, %s) "
            "ON DUPLICATE KEY UPDATE preferences = %s",
            (user_id, json.dumps(preferences), json.dumps(preferences))
        )
        connection.commit()
        return {"status": "Preferences saved successfully"}
    except Error as e:
        return {"error": f"Database error: {str(e)}"}
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

def get_user_preferences(user_id: str) -> Dict[str, Any]:
    connection = get_db_connection()
    if not connection:
        return {"error": "Database connection failed"}
    
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT preferences FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
        if user:
            return json.loads(user["preferences"])
        return {"error": "User not found"}
    except Error as e:
        return {"error": f"Database error: {str(e)}"}
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()
def geocode_location(location: str) -> Dict[str, Any]:
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": location,
        "format": "json",
        "limit": 1
    }
    headers = {"User-Agent": "TravelRecommendation/1.0 (nphu764@gmail.com)"}
    
    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        if data:
            return {
                "lat": float(data[0]["lat"]),
                "lon": float(data[0]["lon"])
            }
        return {"error": "Location not found"}
    except requests.exceptions.RequestException:
        return {"error": "Geocoding error"}

def get_travel_time(origin: str, destination: str, mode: str = "driving") -> Dict[str, Any]:
    connection = get_db_connection()
    if not connection:
        return {"error": "Database connection failed"}
    
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT name, lat, lon FROM destinations WHERE name = %s", (origin,))
        origin_data = cursor.fetchone()
        cursor.execute("SELECT name, lat, lon FROM destinations WHERE name = %s", (destination,))
        destination_data = cursor.fetchone()
        
        if not origin_data or not destination_data:
            origin_coords = geocode_location(origin)
            destination_coords = geocode_location(destination)
            if "error" in origin_coords or "error" in destination_coords:
                return {"error": "Invalid origin or destination"}
        else:
            origin_coords = {"lat": origin_data["lat"], "lon": origin_data["lon"]}
            destination_coords = {"lat": destination_data["lat"], "lon": destination_data["lon"]}
        
        ors_mode = {
            "driving": "driving-car",
            "walking": "foot-walking",
            "bicycling": "cycling-regular"
        }.get(mode, "driving-car")
        
        url = f"https://api.openrouteservice.org/v2/directions/{ors_mode}/geojson"
        headers = {"Authorization": ORS_API_KEY}
        payload = {
            "coordinates": [
                [origin_coords["lon"], origin_coords["lat"]],
                [destination_coords["lon"], destination_coords["lat"]]
            ]
        }
        
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        duration = data["features"][0]["properties"]["segments"][0]["duration"]
        distance = data["features"][0]["properties"]["segments"][0]["distance"]
        
        return {
            "origin": origin,
            "destination": destination,
            "distance": f"{distance / 1000:.2f} km",
            "duration": f"{duration / 60:.2f} mins",
            "duration_seconds": duration
        }
    except requests.exceptions.HTTPError as e:
        return {"error": f"Cannot calculate travel time: {str(e)}"}
    except requests.exceptions.RequestException:
        return {"error": "Network error or API unavailable"}
    except Error as e:
        return {"error": f"Database error: {str(e)}"}
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()