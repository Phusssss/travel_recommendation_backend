
import json
from fastapi import APIRouter, HTTPException
import numpy as np
import mysql.connector
import os
from app.services import get_current_weather, get_travel_time
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

class TravelRecommender:
    def __init__(self):
        """Khởi tạo TravelRecommender với danh sách địa điểm và Q-table."""
        self.destinations = []
        self.n_states = 0
        self.q_table = None
        self.load_destinations()

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
            cursor.execute("SELECT * FROM destinations WHERE city = %s", ("Da Lat",))
            self.destinations = cursor.fetchall()
            self.n_states = len(self.destinations)
            cursor.close()
            conn.close()
            logger.info(f"Loaded {self.n_states} destinations for Da Lat")
            if not self.destinations:
                logger.error("No destinations found in database")
                raise ValueError("No destinations found")
        except Exception as e:
            logger.error(f"Error loading destinations: {e}")
            raise

    def load_q_table(self, city: str):
        try:
            conn = mysql.connector.connect(
                host=os.getenv("DB_HOST", "db"),
                user=os.getenv("DB_USER", "root"),
                password=os.getenv("DB_PASSWORD"),
                database=os.getenv("DB_NAME", "travel_recommendation")
            )
            cursor = conn.cursor()
            cursor.execute("SELECT q_table FROM q_tables WHERE city = %s", (city,))
            result = cursor.fetchone()
            if result:
                q_table_list = json.loads(result[0])
                self.q_table = np.array(q_table_list, dtype=np.float64)
            else:
                self.q_table = np.zeros((self.n_states, self.n_states))
            self.q_table.flags.writeable = True
            cursor.close()
            conn.close()
            logger.info(f"Loaded Q-table for city {city}")
        except Exception as e:
            logger.error(f"Error loading Q-table: {e}")
            self.q_table = np.zeros((self.n_states, self.n_states))
            self.q_table.flags.writeable = True

    def save_q_table(self, city: str):
        try:
            conn = mysql.connector.connect(
                host=os.getenv("DB_HOST", "db"),
                user=os.getenv("DB_USER", "root"),
                password=os.getenv("DB_PASSWORD"),
                database=os.getenv("DB_NAME", "travel_recommendation")
            )
            cursor = conn.cursor()
            q_table_json = json.dumps(self.q_table.tolist())  # Chuyển sang JSON
            cursor.execute(
                "INSERT INTO q_tables (city, q_table) VALUES (%s, %s) ON DUPLICATE KEY UPDATE q_table = %s",
                (city, q_table_json, q_table_json)
            )
            conn.commit()
            cursor.close()
            conn.close()
            logger.info(f"Saved Q-table for city {city}")
        except Exception as e:
            logger.error(f"Error saving Q-table: {e}")

    def train(self, city: str, episodes: int):
        """Huấn luyện mô hình Q-learning."""
        self.load_q_table(city)
        alpha = 0.1  # Learning rate
        gamma = 0.9  # Discount factor
        epsilon = 0.1  # Exploration rate
        for episode in range(episodes):
            current_state = np.random.randint(self.n_states)
            for _ in range(3):  # 3 bước mỗi episode
                if np.random.uniform(0, 1) < epsilon:
                    action = np.random.randint(self.n_states)
                else:
                    action = np.argmax(self.q_table[current_state])
                destination = self.destinations[action]["name"]
                weather = get_current_weather(destination)
                travel_time = get_travel_time(
                    self.destinations[current_state]["name"],
                    destination
                )
                if "error" in weather or "error" in travel_time or travel_time.get("duration") == "N/A":
                    logger.warning(f"Failed to get valid data for {destination}, skipping")
                    continue
                reward = self.calculate_reward(weather, travel_time)
                next_state = action
                self.q_table[current_state, action] = self.q_table[current_state, action] + alpha * (
                    reward + gamma * np.max(self.q_table[next_state]) - self.q_table[current_state, action]
                )
                current_state = next_state
            logger.info(f"Completed training episode {episode + 1}/{episodes}")
        self.save_q_table(city)

    def calculate_reward(self, weather: dict, travel_time: dict) -> float:
        """Tính phần thưởng dựa trên thời tiết và thời gian di chuyển."""
        reward = 0
        if "clear" in weather.get("description", "").lower():
            reward += 10
        duration = float(travel_time.get("duration", "0").split()[0]) if travel_time.get("duration") != "N/A" else 0
        reward -= duration * 0.5
        return reward

    def recommend_route(self, city: str, user_prefs: dict, steps: int) -> list:
        """Đề xuất lộ trình du lịch dựa trên Q-table."""
        self.load_q_table(city)
        route = []
        current_state = np.random.randint(self.n_states)
        for _ in range(steps):
            action = np.argmax(self.q_table[current_state])
            destination = self.destinations[action]["name"]
            weather = get_current_weather(destination)
            travel_time = get_travel_time(
                self.destinations[current_state]["name"],
                destination
            )
            if "error" in weather or "error" in travel_time or travel_time.get("duration") == "N/A":
                logger.warning(f"Failed to get valid data for {destination}, skipping")
                continue
            route.append({
                "destination": destination,
                "weather": weather.get("description", "N/A"),
                "travel_time": travel_time.get("duration", "N/A")
            })
            current_state = action
        return route

@router.post("/train")
async def train_model(city: str, episodes: int = 100):
    """Endpoint để huấn luyện mô hình."""
    try:
        recommender = TravelRecommender()
        recommender.train(city, episodes)
        return {"message": f"Training completed for {city}"}
    except Exception as e:
        logger.error(f"Training failed: {e}")
        raise HTTPException(status_code=500, detail="Training failed")

@router.get("/recommend")
async def recommend_route(city: str, steps: int = 3):
    """Endpoint để đề xuất lộ trình."""
    try:
        recommender = TravelRecommender()
        route = recommender.recommend_route(city, {}, steps)
        if not route:
            raise HTTPException(status_code=404, detail="No route found")
        return route
    except Exception as e:
        logger.error(f"Recommendation failed: {e}")
        raise HTTPException(status_code=500, detail="Recommendation failed")
