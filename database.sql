-- AetherCare Smart Temperature Monitor · MySQL 8+
-- All temperatures are Celsius; seeded ranges are demonstration values only.
CREATE DATABASE IF NOT EXISTS temperature_monitor CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE temperature_monitor;

CREATE TABLE IF NOT EXISTS roles (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(32) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  email VARCHAR(160) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role_id INT NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at DATETIME NOT NULL,
  CONSTRAINT fk_users_role FOREIGN KEY (role_id) REFERENCES roles(id),
  INDEX ix_users_role_active (role_id, active)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS storage_location (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(120) NOT NULL UNIQUE,
  facility VARCHAR(120) NOT NULL DEFAULT 'North Wing',
  created_at DATETIME NOT NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS sensor (
  id INT AUTO_INCREMENT PRIMARY KEY,
  sensor_code VARCHAR(40) NOT NULL UNIQUE,
  location_id INT NOT NULL,
  is_online BOOLEAN NOT NULL DEFAULT TRUE,
  battery_pct INT NOT NULL DEFAULT 92,
  last_seen DATETIME,
  CONSTRAINT fk_sensor_location FOREIGN KEY (location_id) REFERENCES storage_location(id),
  INDEX ix_sensor_location_online (location_id, is_online)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS sensor_status_event (
  id INT AUTO_INCREMENT PRIMARY KEY,
  sensor_id INT NOT NULL,
  is_online BOOLEAN NOT NULL,
  occurred_at DATETIME NOT NULL,
  actor_label VARCHAR(120) NOT NULL DEFAULT 'Monitoring service',
  CONSTRAINT fk_sensor_status_sensor FOREIGN KEY (sensor_id) REFERENCES sensor(id),
  INDEX ix_sensor_status_sensor_time (sensor_id, occurred_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS product (
  id INT AUTO_INCREMENT PRIMARY KEY,
  product_code VARCHAR(40) NOT NULL UNIQUE,
  name VARCHAR(150) NOT NULL,
  category VARCHAR(80) NOT NULL,
  location_id INT NOT NULL,
  sensor_id INT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at DATETIME NOT NULL,
  CONSTRAINT fk_product_location FOREIGN KEY (location_id) REFERENCES storage_location(id),
  CONSTRAINT fk_product_sensor FOREIGN KEY (sensor_id) REFERENCES sensor(id),
  INDEX ix_product_active_location (active, location_id),
  INDEX ix_product_sensor (sensor_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS batch (
  id INT AUTO_INCREMENT PRIMARY KEY,
  product_id INT NOT NULL,
  batch_number VARCHAR(80) NOT NULL UNIQUE,
  created_at DATETIME NOT NULL,
  CONSTRAINT fk_batch_product FOREIGN KEY (product_id) REFERENCES product(id),
  INDEX ix_batch_product (product_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS threshold_version (
  id INT AUTO_INCREMENT PRIMARY KEY,
  product_id INT NOT NULL,
  version INT NOT NULL,
  minimum_c FLOAT NOT NULL,
  maximum_c FLOAT NOT NULL,
  label VARCHAR(160) NOT NULL DEFAULT 'Demonstration threshold — verify locally',
  created_by INT NULL,
  created_at DATETIME NOT NULL,
  CONSTRAINT fk_threshold_product FOREIGN KEY (product_id) REFERENCES product(id),
  CONSTRAINT fk_threshold_user FOREIGN KEY (created_by) REFERENCES users(id),
  CONSTRAINT uq_product_threshold_version UNIQUE (product_id, version),
  INDEX ix_threshold_product_version (product_id, version)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS temperature_reading (
  id INT AUTO_INCREMENT PRIMARY KEY,
  sensor_id INT NOT NULL,
  product_id INT NOT NULL,
  threshold_version_id INT NOT NULL,
  temperature_c FLOAT NOT NULL,
  recorded_at DATETIME NOT NULL,
  simulated BOOLEAN NOT NULL DEFAULT TRUE,
  CONSTRAINT fk_reading_sensor FOREIGN KEY (sensor_id) REFERENCES sensor(id),
  CONSTRAINT fk_reading_product FOREIGN KEY (product_id) REFERENCES product(id),
  CONSTRAINT fk_reading_threshold FOREIGN KEY (threshold_version_id) REFERENCES threshold_version(id),
  INDEX ix_reading_sensor_time (sensor_id, recorded_at),
  INDEX ix_reading_product_time (product_id, recorded_at),
  INDEX ix_reading_threshold (threshold_version_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS incident (
  id INT AUTO_INCREMENT PRIMARY KEY,
  incident_code VARCHAR(32) NOT NULL UNIQUE,
  product_id INT NOT NULL,
  sensor_id INT NOT NULL,
  threshold_version_id INT NOT NULL,
  started_at DATETIME NOT NULL,
  current_excursion_started_at DATETIME NULL,
  recovered_at DATETIME NULL,
  accumulated_seconds INT NOT NULL DEFAULT 0,
  max_temperature_c FLOAT NOT NULL,
  min_temperature_c FLOAT NOT NULL,
  severity VARCHAR(20) NOT NULL DEFAULT 'warning',
  status VARCHAR(20) NOT NULL DEFAULT 'open',
  acknowledged_by INT NULL,
  acknowledged_at DATETIME NULL,
  escalated_at DATETIME NULL,
  assessed_by INT NULL,
  assessed_at DATETIME NULL,
  assessment TEXT NULL,
  CONSTRAINT fk_incident_product FOREIGN KEY (product_id) REFERENCES product(id),
  CONSTRAINT fk_incident_sensor FOREIGN KEY (sensor_id) REFERENCES sensor(id),
  CONSTRAINT fk_incident_threshold FOREIGN KEY (threshold_version_id) REFERENCES threshold_version(id),
  CONSTRAINT fk_incident_ack_user FOREIGN KEY (acknowledged_by) REFERENCES users(id),
  CONSTRAINT fk_incident_assessed_user FOREIGN KEY (assessed_by) REFERENCES users(id),
  INDEX ix_incident_product_status (product_id, status),
  INDEX ix_incident_sensor_status (sensor_id, status),
  INDEX ix_incident_started (started_at),
  INDEX ix_incident_severity_status (severity, status)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS alert (
  id INT AUTO_INCREMENT PRIMARY KEY,
  incident_id INT NULL,
  sensor_id INT NULL,
  alert_type VARCHAR(40) NOT NULL,
  severity VARCHAR(20) NOT NULL,
  message VARCHAR(255) NOT NULL,
  created_at DATETIME NOT NULL,
  acknowledged_by INT NULL,
  acknowledged_at DATETIME NULL,
  CONSTRAINT fk_alert_incident FOREIGN KEY (incident_id) REFERENCES incident(id),
  CONSTRAINT fk_alert_sensor FOREIGN KEY (sensor_id) REFERENCES sensor(id),
  CONSTRAINT fk_alert_user FOREIGN KEY (acknowledged_by) REFERENCES users(id),
  INDEX ix_alert_created (created_at),
  INDEX ix_alert_unacknowledged (acknowledged_at, severity),
  INDEX ix_alert_incident (incident_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS incident_event (
  id INT AUTO_INCREMENT PRIMARY KEY,
  incident_id INT NOT NULL,
  event_type VARCHAR(50) NOT NULL,
  description TEXT NOT NULL,
  actor_id INT NULL,
  actor_label VARCHAR(120) NOT NULL DEFAULT 'System',
  occurred_at DATETIME NOT NULL,
  CONSTRAINT fk_event_incident FOREIGN KEY (incident_id) REFERENCES incident(id),
  CONSTRAINT fk_event_actor FOREIGN KEY (actor_id) REFERENCES users(id),
  INDEX ix_event_incident_time (incident_id, occurred_at),
  INDEX ix_event_time (occurred_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS review_note (
  id INT AUTO_INCREMENT PRIMARY KEY,
  incident_id INT NOT NULL,
  user_id INT NOT NULL,
  note TEXT NOT NULL,
  created_at DATETIME NOT NULL,
  CONSTRAINT fk_review_note_incident FOREIGN KEY (incident_id) REFERENCES incident(id),
  CONSTRAINT fk_review_note_user FOREIGN KEY (user_id) REFERENCES users(id),
  INDEX ix_review_note_incident_time (incident_id, created_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS audit_log (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NULL,
  actor_label VARCHAR(120) NOT NULL,
  action VARCHAR(80) NOT NULL,
  entity_type VARCHAR(60) NOT NULL,
  entity_id VARCHAR(60) NULL,
  details TEXT NULL,
  occurred_at DATETIME NOT NULL,
  CONSTRAINT fk_audit_user FOREIGN KEY (user_id) REFERENCES users(id),
  INDEX ix_audit_actor_time (user_id, occurred_at),
  INDEX ix_audit_entity (entity_type, entity_id),
  INDEX ix_audit_time (occurred_at)
) ENGINE=InnoDB;
