# app/review_analyzer.py
from transformers import pipeline
import mysql.connector
import os
import structlog
from cachetools import TTLCache
from app.services import get_db_connection

logger = structlog.get_logger()

# Bộ nhớ đệm cho kết quả phân tích cảm xúc (TTL = 1 giờ)
sentiment_cache = TTLCache(maxsize=1000, ttl=3600)

# Khởi tạo pipeline phân tích cảm xúc
try:
    sentiment_analyzer = pipeline(
        "sentiment-analysis",
        model="cardiffnlp/twitter-xlm-roberta-base-sentiment",
        tokenizer="cardiffnlp/twitter-xlm-roberta-base-sentiment",
        return_all_scores=True,
        max_length=512,
        truncation=True,
        device=0 if torch.cuda.is_available() else -1  # Dùng GPU nếu có
    )
    logger.info("Initialized sentiment analysis pipeline for Vietnamese")
except Exception as e:
    logger.error("Failed to initialize sentiment pipeline", error=str(e))
    raise

def analyze_review_sentiment(comment: str) -> float:
    """Phân tích cảm xúc của bình luận tiếng Việt và trả về điểm sentiment_score (0-5)."""
    try:
        # Kiểm tra input
        if not comment or not isinstance(comment, str) or comment.strip() == "":
            logger.error("Invalid or empty comment", comment=comment)
            return 0.0

        # Kiểm tra cache
        if comment in sentiment_cache:
            logger.info("Cache hit for sentiment analysis", comment=comment[:50])
            return sentiment_cache[comment]

        # Giới hạn độ dài bình luận
        if len(comment) > 512:
            comment = comment[:512]
            logger.warning("Comment truncated to 512 characters", comment=comment[:50])

        # Phân tích cảm xúc
        results = sentiment_analyzer(comment)[0]
        # Kết quả: [{'label': 'positive', 'score': x}, {'label': 'neutral', 'score': y}, {'label': 'negative', 'score': z}]

        # Tính điểm dựa trên xác suất
        sentiment_score = 0.0
        for result in results:
            label = result["label"]
            score = result["score"]
            if label == "positive":
                sentiment_score += score * 5.0  # Tích cực: 5 điểm
            elif label == "neutral":
                sentiment_score += score * 2.5  # Trung lập: 2.5 điểm
            # Tiêu cực: 0 điểm

        # Chuẩn hóa về thang 0-5
        normalized_score = min(max(round(sentiment_score, 2), 0.0), 5.0)
        sentiment_cache[comment] = normalized_score
        logger.info("Analyzed sentiment", comment=comment[:50], score=normalized_score)
        return normalized_score
    except Exception as e:
        logger.error("Error analyzing sentiment", error=str(e), comment=comment[:50])
        return 0.0

def update_destination_rating(destination_id: int, city_id: int):
    """Cập nhật rating và review_count của địa điểm dựa trên bình luận."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Lấy trung bình sentiment_score từ bảng reviews
        cursor.execute(
            "SELECT AVG(sentiment_score), COUNT(*) FROM reviews "
            "WHERE destination_id = %s AND city_id = %s",
            (destination_id, city_id)
        )
        result = cursor.fetchone()
        avg_score, review_count = (result[0], result[1]) if result[0] is not None else (0.0, 0)

        # Cập nhật rating và review_count trong bảng destinations
        cursor.execute(
            "UPDATE destinations SET rating = %s, review_count = %s "
            "WHERE id = %s AND city_id = %s",
            (avg_score, review_count, destination_id, city_id)
        )
        conn.commit()
        logger.info(
            "Updated destination rating",
            destination_id=destination_id,
            city_id=city_id,
            rating=avg_score,
            review_count=review_count
        )

        cursor.close()
        conn.close()
    except Exception as e:
        logger.error("Error updating destination rating", error=str(e))
        raise

def process_new_review(destination_id: int, city_id: int, comment: str):
    """Xử lý bình luận mới: phân tích cảm xúc và cập nhật rating."""
    try:
        # Validate input
        if not isinstance(destination_id, int) or not isinstance(city_id, int):
            logger.error("Invalid destination_id or city_id", destination_id=destination_id, city_id=city_id)
            raise ValueError("destination_id and city_id must be integers")

        # Validate destination_id và city_id
        from app.services import validate_destination
        if not validate_destination(destination_id, city_id):
            logger.error("Invalid destination or city", destination_id=destination_id, city_id=city_id)
            raise ValueError("Invalid destination or city")

        sentiment_score = analyze_review_sentiment(comment)

        conn = get_db_connection()
        cursor = conn.cursor()

        # Lưu bình luận vào bảng reviews
        cursor.execute(
            "INSERT INTO reviews (destination_id, city_id, comment, sentiment_score) "
            "VALUES (%s, %s, %s, %s)",
            (destination_id, city_id, comment, sentiment_score)
        )
        conn.commit()

        # Cập nhật rating địa điểm
        update_destination_rating(destination_id, city_id)

        cursor.close()
        conn.close()
        logger.info("Processed new review", destination_id=destination_id, city_id=city_id, comment=comment[:50])
        return {"sentiment_score": sentiment_score, "message": "Review processed successfully"}
    except Exception as e:
        logger.error("Error processing review", error=str(e))
        raise