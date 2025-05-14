CREATE DATABASE IF NOT EXISTS travel_recommendation;
USE travel_recommendation;

CREATE TABLE cities (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    country VARCHAR(50) NOT NULL,
    UNIQUE KEY unique_city (name)
);

CREATE TABLE destinations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    city_id INT NOT NULL,
    type VARCHAR(50),
    opening_hours VARCHAR(20),
    ticket_price INT,
    popularity INT,
    latitude FLOAT,
    longitude FLOAT,
    FOREIGN KEY (city_id) REFERENCES cities(id),
    INDEX idx_city_name (city_id, name)
);

CREATE TABLE travel_times (
    id INT AUTO_INCREMENT PRIMARY KEY,
    city_id INT NOT NULL,
    start_location VARCHAR(100) NOT NULL,
    end_location VARCHAR(100) NOT NULL,
    duration VARCHAR(20),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (city_id) REFERENCES cities(id),
    INDEX idx_city_locations (city_id, start_location, end_location)
);

CREATE TABLE q_tables (
    id INT AUTO_INCREMENT PRIMARY KEY,
    city_id INT NOT NULL,
    q_table JSON NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (city_id) REFERENCES cities(id),
    UNIQUE KEY unique_city (city_id)
);

-- Dữ liệu mẫu
INSERT INTO cities (name, country) VALUES
('Da Lat', 'Vietnam'),
('Hanoi', 'Vietnam');

INSERT INTO destinations (name, city_id, type, opening_hours, ticket_price, popularity, latitude, longitude) VALUES
('Ho Xuan Huong', 1, 'sightseeing', '24/7', 0, 8, 11.9411, 108.4378),
('Thung Lung Tinh Yeu', 1, 'sightseeing', '07:00-17:00', 100000, 7, 11.98013826405487, 108.4502269085788),
('Dinh Bao Dai', 1, 'sightseeing', '07:00-17:00', 50000, 6, 11.9475, 108.4317);
INSERT INTO destinations (name, city_id, type, opening_hours, ticket_price, popularity, latitude, longitude) VALUES
('Ho Xuan Huong', 1, 'sightseeing', '24/7', 0, 8, 11.9411, 108.4378),
('Thung Lung Tinh Yeu', 1, 'sightseeing', '07:00-17:00', 100000, 7, 11.9689, 108.4494),
('Dinh Bao Dai', 1, 'sightseeing', '07:00-17:00', 50000, 6, 11.9475, 108.4317),
('Chua Linh Phuoc', 1, 'cultural', '06:00-18:00', 0, 7, 11.944792285320943, 108.49931853863177),
('Thac Datanla', 1, 'nature', '07:00-17:00', 30000, 8, 11.90362135460161, 108.44975353926296), 
('Lang Biang', 1, 'nature', '06:00-18:00', 40000, 6, 12.04810293335689, 108.44162880612551),
('Cho Dem Da Lat', 1, 'market', '17:00-23:00', 0, 9, 11.94151695154275, 108.43732338159225),
('Nha Tho Con Ga', 1, 'cultural', '06:00-18:00', 0, 6, 11.93626793497708, 108.43827992337401),
('Cay Thong Co Don', 1, 'sightseeing', '24/7', 0, 7, 12.020519279237122, 108.38410995275754),
('Ga Da Lat', 1, 'cultural', '07:00-17:00', 5000, 6, 11.941902831261169, 108.45375526624971),, 
('Doi Mong Mo', 1, 'sightseeing', '06:00-18:00', 30000, 8, 11.978082693096328, 108.44549531782617),
('Thac Prenn', 1, 'nature', '07:00-17:00', 40000, 7, 11.87611555914648, 108.47111608389454),
('Ho Tuyen Lam', 1, 'nature', '24/7', 0, 7, 11.895020231088559, 108.4253369737593);