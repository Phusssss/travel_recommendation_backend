
from transformers import pipeline
import unicodedata
import re

def preprocess_vietnamese_text(text: str) -> str:
      """Tiền xử lý văn bản tiếng Việt: chuẩn hóa dấu và loại bỏ ký tự đặc biệt."""
      text = unicodedata.normalize('NFC', text)
      text = text.lower()
      text = re.sub(r'[^\w\s]', '', text)
      return text

  # Khởi tạo mô hình
sentiment_analyzer = pipeline(
      "sentiment-analysis",
      model="nlptown/bert-base-multilingual-uncased-sentiment",
      device=-1
)

  # Test các bình luận
reviews = [
      "Hồ Xuân Hương khá đẹp, nhưng không có gì đặc biệt lắm.",
      "Hồ đẹp nhưng nhiều người quá",
      "Tệ lắm, người dân không thân thiện",
      "Hồ rất đẹp",
      "Tệ"
  ]

  # Tiền xử lý và phân tích
processed_reviews = [preprocess_vietnamese_text(review) for review in reviews]
results = sentiment_analyzer(processed_reviews)
for review, processed, result in zip(reviews, processed_reviews, results):
      score = int(result["label"].split()[0])
      normalized_score = (score - 3) / 2.0
      print(f"Original: {review}")
      print(f"Processed: {processed}")
      print(f"Label: {result['label']}, Raw Score: {score}, Normalized Score: {normalized_score}\n")
