# CampusHire - Modern Campus Recruitment Portal

An end-to-end, full-stack campus recruitment and placement management platform built with Python (Flask), modern CSS (Glassmorphism & animated mesh gradients), Bootstrap 5, and dual database support (SQLite + MySQL).

---

## 🌟 Key Features

1. **Dual Database Architecture (Zero-Setup Instant Run)**:
   - Connects to local MySQL if running (`localhost:3306`, database `campus_recruitment`).
   - Seamlessly auto-falls back to local SQLite (`campus_recruitment.db`) with identical schema, parameterized query abstraction, and automatic seeding.

2. **Attractive Modern UI with Glassmorphic Design**:
   - Deep modern gradient mesh backgrounds with animated floating glow orbs.
   - Frosted glass cards (`backdrop-filter: blur(20px)`), responsive grid layouts, and Google Fonts (`Plus Jakarta Sans`).
   - Dynamic ticker notice banner, partner company showcase, and placement metrics ribbon.

3. **Interactive Profile Picture Options on Login & Register**:
   - **Login Page Avatar Selector & Uploader**: Click the camera badge on the login avatar to choose any custom photo, pick preset avatar styles, or upload from your device.
   - **Dynamic Email Lookup**: Typing a registered email automatically displays that user's saved photo in real time!
   - **Profile Settings (`/profile`)**: Update your profile picture, personal bio, skills, CGPA, and resume anytime.

4. **1-Click Quick Demo Login Chips**:
   - 🎓 **Student Demo**: `student@campus.com` / `student123`
   - 💼 **Recruiter Demo**: `google@campus.com` / `recruiter123`
   - 🛡️ **Admin Demo**: `admin@campus.com` / `admin123`

5. **Realistic Sample Recruitment Drives**:
   - Pre-seeded drives from **Google** (₹24 - 30 LPA), **Microsoft** (₹20 - 26 LPA), **Amazon** (₹18 - 22 LPA), **Goldman Sachs** (₹22 - 28 LPA), **TCS Digital** (₹8.5 - 11 LPA), and **Infosys** (₹9.5 - 13 LPA).

6. **Student Placement Flow**:
   - Browse drives with live keyword & domain search.
   - Check eligibility criteria, work location, package, and application deadline.
   - 1-click drive application with status tracker (`Applied` ➔ `Shortlisted` ➔ `Selected` / `Rejected`).
   - Upload and preview PDF resume.

7. **Recruiter Portal**:
   - Post new recruitment drives with packages, requirements, and deadlines.
   - Review applicant profiles with candidate photos, roll numbers, branches, CGPAs, and download links for resumes.
   - 1-click status transitions (Shortlist, Select, Reject).

8. **Admin Control Center**:
   - Real-time placement metrics: total students, partner companies, published drives, and applications filed.

---

## 🚀 Quick Start Guide

### 1. Requirements
- Python 3.8+
- Flask (`pip install -r requirements.txt`)

### 2. Run the Application
```bash
python app.py
```
Open your browser and navigate to:
```
http://127.0.0.1:5000
```

---

## 🔐 Demo Credentials

| Role | Email | Password | Access / Features |
| :--- | :--- | :--- | :--- |
| **Student** | `student@campus.com` | `student123` | Browse drives, 1-click apply, view application timeline |
| **Student 2** | `priya@campus.com` | `student123` | Dean's lister candidate with selected status |
| **Company** | `google@campus.com` | `recruiter123` | Post drives, review candidate resumes & photos, update status |
| **Company 2** | `microsoft@campus.com` | `recruiter123` | Azure Cloud drive recruiter |
| **Admin** | `admin@campus.com` | `admin123` | Placement analytics and system overview |

---

## 📁 Project Structure

```
CampusRecruitmentPortal/
│
├── app.py                     # Main Flask web application & route controller
├── db.py                      # Database abstraction layer (MySQL & SQLite fallback)
├── database.sql               # MySQL relational database schema & seed scripts
├── campus_recruitment.db      # SQLite database (auto-created & pre-seeded)
├── requirements.txt           # Python dependencies
├── README.md                  # Project documentation
│
├── templates/                 # Jinja2 HTML Templates
│   ├── base.html              # Common layout, modern navbar & footer
│   ├── index.html             # Enhanced landing & home page
│   ├── home.html              # Home page alias
│   ├── login.html             # Glassmorphic login with avatar uploader & demo chips
│   ├── register.html          # Registration with role toggle & photo upload
│   ├── dashboard.html         # Role-specific dashboards (Admin, Student, Company)
│   ├── jobs.html              # Drive directory with live search & filter
│   ├── job_details.html       # Drive overview, CTC details, and 1-click apply
│   ├── post_job.html          # Recruiter drive publishing form
│   ├── applicants.html        # Recruiter applicant review with candidate photos & CVs
│   └── profile.html           # User profile editor (photo, resume, bio, skills)
│
└── static/
    ├── css/
    │   └── style.css          # Modern styling, mesh gradients, glassmorphic cards
    ├── js/
    │   └── main.js            # Interactive avatar preview, demo autofill & search
    └── uploads/
        ├── avatars/           # Uploaded profile photos
        └── resumes/           # Uploaded candidate PDF resumes
```
