import requests
from app.services import get_current_weather, get_travel_time
from fastapi import APIRouter, HTTPException, Body, Query
import numpy as np
import mysql.connector
import os
import json
import structlog
from urllib.error import HTTPError

router = APIRouter()
logger = structlog.get_logger()

class TravelRecommender:
    def __init__(self, city: str):
        """Khởi tạo TravelRecommender với danh sách địa điểm và Q-table."""
        self.city = city
        self.city_id = self.get_city_id(city)
        self.destinations = []
        self.n_states = 0
        self.q_table = None
        self.load_destinations()

    def get_city_id(self, city: str) -> int:
        """Lấy city_id từ bảng cities dựa trên tên thành phố."""
        try:
            conn = mysql.connector.connect(
                host=os.getenv("DB_HOST", "db"),
                user=os.getenv("DB_USER", "root"),
                password=os.getenv("DB_PASSWORD"),
                database=os.getenv("DB_NAME", "travel_recommendation")
            )
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

    def load_destinations(self):
        """Tải danh sách địa điểm từ database."""
        try:
            conn = mysql.connector.connect(
                host=os.getenv("DB_HOST", "db"),
                user=os.getenv("DB_USER", "root"),
                password=os.getenv("DB_PASSWORD"),
                database=os.getenv("DB_NAME", "travel_recommendation")
            )
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM destinations WHERE city_id = %s", (self.city_id,))
            self.destinations = cursor.fetchall()
            self.n_states = len(self.destinations)
            cursor.close()
            conn.close()
            logger.info("Loaded destinations", city=self.city, count=self.n_states)
            if not self.destinations:
                logger.error("No destinations found", city=self.city)
                raise ValueError(f"No destinations found for city {self.city}")
        except Exception as e:
            logger.error("Error loading destinations", error=str(e))
            raise

    def load_q_table(self):
        """Tải Q-table từ database."""
        try:
            conn = mysql.connector.connect(
                host=os.getenv("DB_HOST", "db"),
                user=os.getenv("DB_USER", "root"),
                password=os.getenv("DB_PASSWORD"),
                database=os.getenv("DB_NAME", "travel_recommendation")
            )
            cursor = conn.cursor()
            cursor.execute("SELECT q_table FROM q_tables WHERE city_id = %s", (self.city_id,))
            result = cursor.fetchone()
            if result:
                q_table_list = json.loads(result[0])
                self.q_table = np.array(q_table_list, dtype=np.float64)
            else:
                self.q_table = np.zeros((self.n_states, self.n_states))
            self.q_table.flags.writeable = True
            cursor.close()
            conn.close()
            logger.info("Loaded Q-table", city=self.city)
        except Exception as e:
            logger.error("Error loading Q-table", error=str(e))
            self.q_table = np.zeros((self.n_states, self.n_states))
            self.q_table.flags.writeable = True

    def save_q_table(self):
        """Lưu Q-table vào database."""
        try:
            conn = mysql.connector.connect(
                host=os.getenv("DB_HOST", "db"),
                user=os.getenv("DB_USER", "root"),
                password=os.getenv("DB_PASSWORD"),
                database=os.getenv("DB_NAME", "travel_recommendation")
            )
            cursor = conn.cursor()
            q_table_json = json.dumps(self.q_table.tolist())
            cursor.execute(
                "INSERT INTO q_tables (city_id, q_table) VALUES (%s, %s) ON DUPLICATE KEY UPDATE q_table = %s",
                (self.city_id, q_table_json, q_table_json)
            )
            conn.commit()
            cursor.close()
            conn.close()
            logger.info("Saved Q-table", city=self.city)
        except Exception as e:
            logger.error("Error saving Q-table", error=str(e))

    def train(self, episodes: int, user_prefs: dict = None):
        """Huấn luyện mô hình Q-learning."""
        self.load_q_table()
        alpha = 0.1  # Learning rate
        gamma = 0.9  # Discount factor
        epsilon = 0.1  # Exploration rate
        user_prefs = user_prefs or {}
        for episode in range(episodes):
            current_state = np.random.randint(self.n_states)
            for _ in range(3):  # 3 bước mỗi episode
                if np.random.uniform(0, 1) < epsilon:
                    action = np.random.randint(self.n_states)
                else:
                    action = np.argmax(self.q_table[current_state])
                destination = self.destinations[action]["name"]
                weather = get_current_weather(self.city)
                travel_time = get_travel_time(
                    self.destinations[current_state]["name"],
                    destination,
                    self.city
                )
                if "error" in weather or "error" in travel_time or travel_time.get("duration") == "N/A":
                    logger.warning("Failed to get valid data", destination=destination)
                    continue
                reward = self.calculate_reward(weather, travel_time, self.destinations[action], user_prefs)
                next_state = action
                self.q_table[current_state, action] = self.q_table[current_state, action] + alpha * (
                    reward + gamma * np.max(self.q_table[next_state]) - self.q_table[current_state, action]
                )
                current_state = next_state
            logger.info("Completed training episode", episode=episode + 1, total=episodes)
        self.save_q_table()

    def calculate_reward(self, weather: dict, travel_time: dict, destination: dict, user_prefs: dict) -> float:
        """Tính phần thưởng dựa trên thời tiết, thời gian di chuyển, và sở thích người dùng."""
        reward = 0
        if "clear" in weather.get("description", "").lower():
            reward += 10
        elif "rain" in weather.get("description", "").lower():
            reward -= 5
        reward += weather.get("temperature", 0) * 0.2

        duration = float(travel_time.get("duration", "0").split()[0]) if travel_time.get("duration") != "N/A" else 0
        reward -= duration * 0.5

        if user_prefs.get("preferred_type") and user_prefs.get("preferred_type") == destination.get("type"):
            reward += 15
        ticket_price = destination.get("ticket_price", 0)
        reward -= ticket_price / 10000
        reward += destination.get("popularity", 0) * 2
        return reward

    def recommend_route(self, user_prefs: dict, steps: int) -> list:
        """Đề xuất lộ trình du lịch dựa trên Q-table và sở thích người dùng."""
        if self.q_table is None:
            self.load_q_table()
        if not np.any(self.q_table):
            logger.error("Q-table not trained", city=self.city)
            raise ValueError("Q-table not trained")

        preferred_type = user_prefs.get("preferred_type", "")
        max_budget = user_prefs.get("max_budget", float("inf"))

        valid_destinations = [
            i for i, dest in enumerate(self.destinations)
            if (not preferred_type or dest["type"] == preferred_type)
            and (dest.get("ticket_price", 0) <= max_budget)
        ]
        if not valid_destinations:
            logger.error("No destinations match user preferences", user_prefs=user_prefs)
            raise ValueError("No destinations match your preferences or budget")

        route = []
        current_state = np.random.choice(valid_destinations)
        visited = set()
        total_budget = 0

        for _ in range(min(steps, len(valid_destinations))):
            valid_actions = [
                i for i in valid_destinations
                if self.destinations[i]["name"] not in visited
            ]
            if not valid_actions:
                break

            action = max(valid_actions, key=lambda x: self.q_table[current_state][x])
            destination = self.destinations[action]["name"]
            ticket_price = self.destinations[action].get("ticket_price", 0)

            if total_budget + ticket_price > max_budget:
                logger.warning("Exceeds budget", destination=destination, total_budget=total_budget)
                continue

            weather = get_current_weather(self.city)
            travel_time = get_travel_time(
                self.destinations[current_state]["name"],
                destination,
                self.city
            )
            if "error" in weather or "error" in travel_time or travel_time.get("duration") == "N/A":
                logger.warning("Failed to get valid data", destination=destination)
                continue

            total_budget += ticket_price
            route.append({
                "destination": destination,
                "weather": weather.get("description", "N/A"),
                "temperature": weather.get("temperature", "N/A"),
                "travel_time": travel_time.get("duration", "N/A"),
                "ticket_price": ticket_price
            })
            visited.add(destination)
            current_state = action

        if not route:
            raise ValueError("Could not generate a valid route")
        return route

@router.post("/train")
async def train_model(request: dict = Body(...)):
    """Endpoint để huấn luyện mô hình."""
    city = request.get("city")
    episodes = request.get("episodes", 100)
    user_prefs = request.get("user_prefs", None)

    if not city:
        logger.error("Missing city parameter")
        raise HTTPException(status_code=400, detail="City is required")

    logger.info("Received train request", city=city, episodes=episodes, user_prefs=user_prefs)
    try:
        recommender = TravelRecommender(city)
        recommender.train(episodes, user_prefs)
        return {"message": f"Training completed for {city}"}
    except Exception as e:
        logger.error("Training failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Training failed: {str(e)}")

@router.get("/recommend")
async def recommend_route(
    city: str,
    steps: int = Query(3, ge=1),
    preferred_type: str = Query("", description="Preferred destination type (e.g., natural, cultural)"),
    max_budget: float = Query(float("inf"), ge=0, description="Maximum budget for ticket prices")
):
    """Endpoint để đề xuất lộ trình."""
    logger.info("Received recommend request", city=city, steps=steps, preferred_type=preferred_type, max_budget=max_budget)
    try:
        recommender = TravelRecommender(city)
        user_prefs = {"preferred_type": preferred_type, "max_budget": max_budget}
        route = recommender.recommend_route(user_prefs, steps)
        if not route:
            raise HTTPException(status_code=404, detail="No route found")
        return route
    except ValueError as e:
        logger.error("Recommendation failed", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Recommendation failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Recommendation failed: {str(e)}")

@router.get("/coordinates")
async def get_location_coordinates(
    location: str,
    city: str
):
    """Endpoint để lấy tọa độ của một địa điểm."""
    logger.info("Received coordinates request", location=location, city=city)
    try:
        from app.services import get_coordinates
        coords = get_coordinates(location, city)
        if not coords:
            raise HTTPException(status_code=404, detail=f"Coordinates not found for {location} in {city}")
        return {
            "latitude": coords[1],
            "longitude": coords[0]
        }
    except ValueError as e:
        logger.error("Coordinates request failed", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Coordinates request failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get coordinates: {str(e)}")

@router.post("/route")
async def get_route_directions(request: dict = Body(...)):
    """Lấy hướng dẫn tuyến đường từ ORS."""
    api_key = os.getenv("ORS_API_KEY")
    if not api_key:
        logger.error("ORS_API_KEY not set")
        raise HTTPException(status_code=500, detail="Missing ORS_API_KEY")

    coordinates = request.get("coordinates")  # [[lon, lat], [lon, lat], ...]
    if not coordinates or len(coordinates) < 2:
        logger.error("Invalid coordinates")
        raise HTTPException(status_code=400, detail="At least two coordinates are required")

    headers = {"Authorization": api_key, "Content-Type": "application/json"}
    body = {"coordinates": coordinates}
    try:
        response = requests.post(
            "https://api.openrouteservice.org/v2/directions/driving-car",
            json=body,
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()

        # Kiểm tra xem data có phải là dictionary không
        if not isinstance(data, dict):
            logger.error("Invalid response from ORS", response=data)
            raise HTTPException(status_code=500, detail=f"Invalid response format from ORS: {data}")

        # Lấy thông tin tuyến đường
        routes = data.get("routes", [])
        if not routes:
            logger.error("No routes found in ORS response")
            raise HTTPException(status_code=404, detail="No routes found in ORS response")

        # Lấy tọa độ và hướng dẫn
        instructions = routes[0].get("segments", [{}])[0].get("steps", [])
        translated_instructions = [
            {
                "text": translate_instruction(step.get("instruction", "Unknown")),
                "distance": step.get("distance", 0),
                "duration": step.get("duration", 0)
            }
            for step in instructions
        ]
        return {
            "coordinates": routes[0].get("geometry", {}).get("coordinates", []),
            "instructions": translated_instructions
        }
    except requests.HTTPError as e:
        error_detail = str(e)
        if e.response:
            error_detail += f" - {e.response.text}"
        logger.error("Error fetching route directions", error=error_detail)
        raise HTTPException(status_code=500, detail=f"Failed to get route directions: {error_detail}")
    except Exception as e:
        logger.error("Error fetching route directions", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get route directions: {str(e)}")

def translate_instruction(instruction: str) -> str:
    """Dịch hướng dẫn sang tiếng Việt (cơ bản)."""
    translations = {
        "Turn left": "Rẽ trái",
        "Turn right": "Rẽ phải",
        "Continue": "Tiếp tục đi thẳng",
        "Take the ramp": "Đi vào đường dẫn",
        "Arrive at destination": "Đến nơi",
        "Head": "Đi thẳng",
        "Turn around": "Quay đầu",
        "Enter roundabout": "Vào vòng xuyến",
        "Exit roundabout": "Rời vòng xuyến"
    }
    return translations.get(instruction, instruction)