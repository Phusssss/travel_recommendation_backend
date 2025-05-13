CREATE DATABASE IF NOT EXISTS travel_recommendation;
     USE travel_recommendation;

     CREATE TABLE destinations (
         id INT AUTO_INCREMENT PRIMARY KEY,
         name VARCHAR(100) NOT NULL,
         city VARCHAR(50) NOT NULL,
         type VARCHAR(50),
         opening_hours VARCHAR(20),
         ticket_price INT,
         popularity INT,
         lat FLOAT,
         lon FLOAT
     );
    CREATE TABLE users (
    user_id VARCHAR(50) PRIMARY KEY,
    preferences JSON
);
     INSERT INTO destinations (name, city, type, opening_hours, ticket_price, popularity, lat, lon) VALUES
     ('Ho Xuan Huong', 'Da Lat', 'sightseeing', '24/7', 0, 8, 11.9411, 108.4378),
     ('Thung Lung Tinh Yeu', 'Da Lat', 'sightseeing', '07:00-17:00', 100000, 7, 11.9689, 108.4494),
     ('Dinh Bao Dai', 'Da Lat', 'sightseeing', '07:00-17:00', 50000, 6, 11.9475, 108.4317);