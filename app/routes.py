from fastapi import APIRouter, Query
from app.services import get_current_weather, get_user_preferences, get_weather_forecast, get_weather_by_coordinates, get_travel_time, get_db_connection, save_user_preferences
from typing import Dict, Any, List
import numpy as np
from mysql.connector import Error
from fastapi import Body
router = APIRouter()

@router.get("/weather/current")
def fetch_current_weather(city: str) -> Dict[str, Any]:
    return get_current_weather(city)

@router.get("/weather/forecast")
def fetch_weather_forecast(city: str, days: int = Query(5, ge=1, le=5)) -> Dict[str, Any]:
    return get_weather_forecast(city, days)

@router.get("/weather/coordinates")
def fetch_weather_by_coordinates(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180)) -> Dict[str, Any]:
    return get_weather_by_coordinates(lat, lon)
@router.post("/user/preferences")
def save_preferences(user_id: str, preferences: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    return save_user_preferences(user_id, preferences)

@router.get("/user/preferences")
def fetch_preferences(user_id: str) -> Dict[str, Any]:
    return get_user_preferences(user_id)
@router.get("/travel/time")
def fetch_travel_time(
    origin: str = Query(..., description="Điểm xuất phát"),
    destination: str = Query(..., description="Điểm đến"),
    mode: str = Query("driving", enum=["driving", "walking", "bicycling"])
) -> Dict[str, Any]:
    return get_travel_time(origin, destination, mode)

@router.get("/destinations")
def fetch_destinations(city: str) -> List[Dict[str, Any]]:
    connection = get_db_connection()
    if not connection:
        return {"error": "Database connection failed"}
    
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM destinations WHERE city = %s", (city,))
        destinations = cursor.fetchall()
        return destinations
    except Error as e:
        return {"error": f"Database error: {str(e)}"}
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

class TravelRecommender:
    def __init__(self, destinations: List[Dict[str, Any]]):
        self.destinations = destinations
        self.n_states = len(destinations)
        self.q_table = np.zeros((self.n_states, self.n_states))
        self.alpha = 0.1
        self.gamma = 0.9
        self.epsilon = 0.1

    def get_reward(self, current_state: int, action: int, weather: Dict, travel_time: Dict, user_prefs: Dict = None) -> float:
        destination = self.destinations[action]
        weather_condition = weather.get("weather", [{}])[0].get("main", "")
        travel_duration = travel_time.get("duration_seconds", 0)
        
        reward = destination["popularity"] * 10
        if weather_condition in ["Rain", "Storm"]:
            reward -= 20
        reward -= travel_duration / 60
        if user_prefs and destination["type"] in user_prefs.get("activities", []):
            reward += 15
        if user_prefs and destination["ticket_price"] > user_prefs.get("budget", float("inf")):
            reward -= 50
        return reward

    def choose_action(self, state: int) -> int:
        if np.random.uniform(0, 1) < self.epsilon:
            return np.random.randint(self.n_states)
        return np.argmax(self.q_table[state])

    def update_q_table(self, state: int, action: int, reward: float, next_state: int):
        self.q_table[state, action] = (1 - self.alpha) * self.q_table[state, action] + \
            self.alpha * (reward + self.gamma * np.max(self.q_table[next_state]))

    def recommend_route(self, start_city: str, user_prefs: Dict = None, num_steps: int = 3) -> List[Dict]:
        route = []
        current_state = 0

        for _ in range(num_steps):
            action = self.choose_action(current_state)
            next_destination = self.destinations[action]
            
            weather = get_current_weather(start_city)
            travel_time = get_travel_time(
                self.destinations[current_state]["name"],
                next_destination["name"]
            )
            
            reward = self.get_reward(current_state, action, weather, travel_time, user_prefs)
            next_state = action
            
            self.update_q_table(current_state, action, reward, next_state)
            route.append({
                "destination": next_destination["name"],
                "weather": weather.get("weather", [{}])[0].get("description", ""),
                "travel_time": travel_time.get("duration", "Unknown")
            })
            current_state = next_state

        return route

@router.get("/recommend")
def recommend_route(
    city: str,
    user_id: str = Query(None, description="ID người dùng để lấy sở thích"),
    steps: int = Query(3, ge=1, le=10)
) -> List[Dict[str, Any]]:
    connection = get_db_connection()
    if not connection:
        return {"error": "Database connection failed"}
    
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM destinations WHERE city = %s", (city,))
        destinations = cursor.fetchall()
        if not destinations:
            return {"error": "No destinations found for this city"}
        
        user_prefs = get_user_preferences(user_id) if user_id else {}
        if "error" in user_prefs:
            user_prefs = {}
        
        recommender = TravelRecommender(destinations)
        route = recommender.recommend_route(city, user_prefs, steps)
        return route
    except Error as e:
        return {"error": f"Database error: {str(e)}"}
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()