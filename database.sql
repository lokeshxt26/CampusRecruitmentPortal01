-- Campus Recruitment Portal Database Schema (MySQL Compatible)

CREATE DATABASE IF NOT EXISTS campus_recruitment;
USE campus_recruitment;

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    role ENUM('admin','student','company') NOT NULL,
    phone VARCHAR(20) DEFAULT '',
    profile_pic VARCHAR(255) DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS students (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    roll_no VARCHAR(50),
    branch VARCHAR(50),
    year VARCHAR(20),
    cgpa DECIMAL(3,2) DEFAULT 0.0,
    phone VARCHAR(20),
    resume VARCHAR(255) DEFAULT '',
    skills TEXT,
    bio TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS companies (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    company_name VARCHAR(150),
    website VARCHAR(150),
    location VARCHAR(100),
    logo VARCHAR(255) DEFAULT '',
    description TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS jobs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    company_id INT NOT NULL,
    title VARCHAR(150) NOT NULL,
    description TEXT,
    eligibility VARCHAR(255),
    salary VARCHAR(100),
    location VARCHAR(100),
    job_type VARCHAR(50) DEFAULT 'Full Time',
    skills VARCHAR(255) DEFAULT '',
    deadline DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS applications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    job_id INT NOT NULL,
    student_id INT NOT NULL,
    status ENUM('Applied','Shortlisted','Rejected','Selected') DEFAULT 'Applied',
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);

-- Default Administrator
INSERT IGNORE INTO users (name, email, password, role, profile_pic)
VALUES ('System Administrator', 'admin@campus.com', 'admin123', 'admin', 'https://api.dicebear.com/7.x/bottts/svg?seed=admin');