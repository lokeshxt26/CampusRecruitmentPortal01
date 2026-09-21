import os
import re
import uuid
import random
import secrets
import urllib.parse
import requests
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

from flask import (
    Flask, render_template, request, redirect, session, flash, jsonify, url_for
)
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from db import get_db, init_db
import sms_service

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "campus_recruitment_portal_super_secret_key_2026")

# Apply ProxyFix middleware so redirect_uri uses https on Render / reverse proxies
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Configure Upload Folders
UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads")
AVATARS_FOLDER = os.path.join(UPLOAD_FOLDER, "avatars")
RESUMES_FOLDER = os.path.join(UPLOAD_FOLDER, "resumes")

os.makedirs(AVATARS_FOLDER, exist_ok=True)
os.makedirs(RESUMES_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max upload size

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "svg"}
ALLOWED_DOC_EXTENSIONS = {"pdf", "doc", "docx"}


def allowed_file(filename, allowed_set):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_set


def save_file(file_storage, target_folder, allowed_set):
    """Safely saves an uploaded file and returns its relative static URL."""
    if not file_storage or file_storage.filename == "":
        return None
    if allowed_file(file_storage.filename, allowed_set):
        ext = file_storage.filename.rsplit(".", 1)[1].lower()
        unique_name = f"{uuid.uuid4().hex}.{ext}"
        file_path = os.path.join(target_folder, unique_name)
        file_storage.save(file_path)
        rel_folder = os.path.basename(target_folder)
        return f"/static/uploads/{rel_folder}/{unique_name}"
    return None


# Initialize Database & Seed data on boot
with app.app_context():
    init_db()


@app.context_processor
def inject_user_context():
    """Make current user avatar and info accessible across all templates."""
    user_avatar = session.get("profile_pic", "")
    return dict(current_user_avatar=user_avatar)


# -------------------------------------------------------------
# HOME & BROWSE RECRUITMENT DRIVES
# -------------------------------------------------------------

@app.route("/")
@app.route("/home")
def index():
    query = request.args.get("q", "").strip()
    if query:
        return redirect(url_for("jobs", q=query))

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT jobs.*, companies.company_name, companies.logo
        FROM jobs
        JOIN companies ON jobs.company_id = companies.id
        ORDER BY jobs.created_at DESC
        LIMIT 9
    """)
    jobs = cursor.fetchall()

    cursor.execute("""
        SELECT companies.*, COUNT(jobs.id) AS open_roles
        FROM companies
        LEFT JOIN jobs ON companies.id = jobs.company_id
        GROUP BY companies.id
        ORDER BY open_roles DESC
        LIMIT 8
    """)
    featured_companies = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) AS total_jobs FROM jobs")
    total_jobs = cursor.fetchone()["total_jobs"]

    cursor.execute("SELECT COUNT(*) AS total_companies FROM companies")
    total_companies = cursor.fetchone()["total_companies"]

    cursor.execute("SELECT COUNT(*) AS total_students FROM students")
    total_students = cursor.fetchone()["total_students"]

    cursor.execute("SELECT COUNT(*) AS total_apps FROM applications")
    total_apps = cursor.fetchone()["total_apps"]

    cursor.close()
    db.close()

    stats = {
        "jobs": total_jobs,
        "companies": total_companies,
        "students": total_students,
        "applications": total_apps
    }

    return render_template("index.html", jobs=jobs, featured_companies=featured_companies, stats=stats)


@app.route("/jobs")
def jobs():
    query = request.args.get("q", "").strip()
    company_filter = request.args.get("company", "").strip()
    location_filter = request.args.get("location", "").strip()
    domain_filter = request.args.get("domain", "").strip()
    type_filter = request.args.get("type", "").strip()

    db = get_db()
    cursor = db.cursor(dictionary=True)

    sql = """
        SELECT jobs.*, companies.company_name, companies.logo
        FROM jobs
        JOIN companies ON jobs.company_id = companies.id
        WHERE 1=1
    """
    params = []

    if query:
        sql += """ AND (
            LOWER(jobs.title) LIKE %s OR
            LOWER(companies.company_name) LIKE %s OR
            LOWER(jobs.skills) LIKE %s OR
            LOWER(jobs.description) LIKE %s OR
            LOWER(jobs.location) LIKE %s OR
            LOWER(jobs.eligibility) LIKE %s OR
            LOWER(jobs.job_type) LIKE %s OR
            LOWER(jobs.salary) LIKE %s
        )"""
        p = f"%{query.lower()}%"
        params.extend([p, p, p, p, p, p, p, p])

    if company_filter:
        sql += " AND LOWER(companies.company_name) LIKE %s"
        params.append(f"%{company_filter.lower()}%")

    if location_filter:
        sql += " AND LOWER(jobs.location) LIKE %s"
        params.append(f"%{location_filter.lower()}%")

    if domain_filter:
        sql += " AND (LOWER(jobs.title) LIKE %s OR LOWER(jobs.skills) LIKE %s OR LOWER(jobs.description) LIKE %s)"
        p_d = f"%{domain_filter.lower()}%"
        params.extend([p_d, p_d, p_d])

    if type_filter:
        sql += " AND LOWER(jobs.job_type) LIKE %s"
        params.append(f"%{type_filter.lower()}%")

    sql += " ORDER BY jobs.created_at DESC"

    cursor.execute(sql, tuple(params))
    all_jobs = cursor.fetchall()

    cursor.execute("SELECT DISTINCT company_name FROM companies ORDER BY company_name")
    company_names = [r["company_name"] for r in cursor.fetchall()]

    cursor.execute("SELECT DISTINCT location FROM jobs WHERE location IS NOT NULL AND location != '' ORDER BY location")
    locations = [r["location"] for r in cursor.fetchall()]

    cursor.close()
    db.close()

    return render_template(
        "jobs.html",
        jobs=all_jobs,
        query=query,
        company_filter=company_filter,
        location_filter=location_filter,
        domain_filter=domain_filter,
        type_filter=type_filter,
        company_names=company_names,
        locations=locations
    )


@app.route("/job/<int:job_id>")
def job_details(job_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT jobs.*, companies.company_name, companies.website, companies.location AS company_location, 
               companies.logo, companies.description AS company_description
        FROM jobs
        JOIN companies ON jobs.company_id = companies.id
        WHERE jobs.id = %s
    """, (job_id,))
    job = cursor.fetchone()

    if not job:
        cursor.close()
        db.close()
        flash("Recruitment drive not found.", "warning")
        return redirect("/jobs")

    has_applied = False
    if "user_id" in session and session.get("role") == "student":
        cursor.execute("SELECT id FROM students WHERE user_id = %s", (session["user_id"],))
        student = cursor.fetchone()
        if student:
            cursor.execute("""
                SELECT id FROM applications
                WHERE job_id = %s AND student_id = %s
            """, (job_id, student["id"]))
            if cursor.fetchone():
                has_applied = True

    cursor.close()
    db.close()
    return render_template("job_details.html", job=job, has_applied=has_applied)


# -------------------------------------------------------------
# AUTHENTICATION: REGISTER & LOGIN
# -------------------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "student")

        if not name or not email or not password:
            flash("All required fields must be filled out.", "danger")
            return redirect("/register")

        # Handle Profile Picture
        profile_pic = ""
        # 1) File upload check
        if "profile_picture" in request.files:
            uploaded_pic = save_file(request.files["profile_picture"], AVATARS_FOLDER, ALLOWED_IMAGE_EXTENSIONS)
            if uploaded_pic:
                profile_pic = uploaded_pic
        # 2) Preset avatar fallback
        if not profile_pic:
            preset = request.form.get("preset_avatar", "").strip()
            if preset:
                profile_pic = preset
            else:
                profile_pic = f"https://api.dicebear.com/7.x/initials/svg?seed={name}"

        db = get_db()
        cursor = db.cursor(dictionary=True)

        try:
            # Check existing email
            cursor.execute("SELECT id FROM users WHERE LOWER(email) = %s", (email,))
            if cursor.fetchone():
                flash("An account with this email already exists. Please log in or use Forgot Password.", "warning")
                cursor.close()
                db.close()
                return redirect("/login")

            phone_raw = request.form.get("phone", "").strip()
            digits_phone = re.sub(r"\D", "", phone_raw)
            phone = digits_phone[-10:] if len(digits_phone) >= 10 else phone_raw

            # Insert user
            cursor.execute("""
                INSERT INTO users (name, email, password, role, profile_pic, phone)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (name, email, password, role, profile_pic, phone))
            user_id = cursor.lastrowid

            if role == "student":
                # Handle Resume Upload
                resume_url = ""
                if "resume_file" in request.files:
                    uploaded_resume = save_file(request.files["resume_file"], RESUMES_FOLDER, ALLOWED_DOC_EXTENSIONS)
                    if uploaded_resume:
                        resume_url = uploaded_resume

                cgpa_raw = request.form.get("cgpa", "").strip()
                try:
                    cgpa_matches = re.findall(r"[-+]?(?:\d*\.\d+|\d+)", cgpa_raw)
                    cgpa_val = float(cgpa_matches[0]) if cgpa_matches else 0.0
                except Exception:
                    cgpa_val = 0.0

                cursor.execute("""
                    INSERT INTO students (user_id, roll_no, branch, year, cgpa, phone, resume, skills)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    user_id,
                    request.form.get("roll_no", ""),
                    request.form.get("branch", ""),
                    request.form.get("year", ""),
                    cgpa_val,
                    phone,
                    resume_url,
                    request.form.get("skills", "")
                ))

            elif role == "company":
                company_logo = request.form.get("company_logo", "").strip()
                if not company_logo:
                    company_logo = profile_pic
                cursor.execute("""
                    INSERT INTO companies (user_id, company_name, website, location, logo, description)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    user_id,
                    request.form.get("company_name", name),
                    request.form.get("website", ""),
                    request.form.get("location", ""),
                    company_logo,
                    request.form.get("description", "")
                ))

            # If admin, user is already created in users table with role='admin'

            db.commit()
            flash(f"Registration successful for {name}! You can now log in.", "success")
            cursor.close()
            db.close()
            return redirect("/login")

        except Exception as e:
            db.rollback()
            cursor.close()
            db.close()
            flash(f"Registration error: {str(e)}", "danger")
            return redirect("/register")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        raw_identifier = request.form.get("email", "").strip()
        identifier = raw_identifier.lower()
        password = request.form.get("password", "").strip()
        login_role = request.form.get("login_role", "").strip().lower()

        if not raw_identifier or not password:
            flash("Please enter both email/phone and password.", "warning")
            return redirect("/login")

        db = get_db()
        cursor = db.cursor(dictionary=True)

        # Match by email or normalized phone number
        clean_digits = re.sub(r"\D", "", raw_identifier)
        if len(clean_digits) >= 10:
            phone_last10 = clean_digits[-10:]
            cursor.execute("""
                SELECT * FROM users 
                WHERE LOWER(email) = %s 
                   OR phone = %s 
                   OR phone LIKE %s
            """, (identifier, raw_identifier, f"%{phone_last10}"))
        else:
            cursor.execute("SELECT * FROM users WHERE LOWER(email) = %s OR phone = %s", (identifier, raw_identifier))
            
        user = cursor.fetchone()

        if not user:
            cursor.close()
            db.close()
            flash("No account registered with this email or phone. Please verify or register a new account.", "danger")
            return redirect("/login")

        if user["password"] != password:
            cursor.close()
            db.close()
            flash("Incorrect password. Please try again or use 'Forgot Password?'.", "danger")
            return redirect("/login")

        if login_role == "admin" and user["role"] != "admin":
            cursor.close()
            db.close()
            flash("Access denied. This account does not have Administrator privileges.", "danger")
            return redirect("/login")

        # Check if user opted to add/update profile picture right on the login page!
        new_avatar = None
        if "profile_picture" in request.files:
            uploaded_avatar = save_file(request.files["profile_picture"], AVATARS_FOLDER, ALLOWED_IMAGE_EXTENSIONS)
            if uploaded_avatar:
                new_avatar = uploaded_avatar

        preset_avatar = request.form.get("preset_avatar", "").strip()
        if not new_avatar and preset_avatar:
            new_avatar = preset_avatar

        if new_avatar:
            cursor.execute("UPDATE users SET profile_pic = %s WHERE id = %s", (new_avatar, user["id"]))
            db.commit()
            user["profile_pic"] = new_avatar

        # Populate session
        session["user_id"] = user["id"]
        session["name"] = user["name"]
        session["email"] = user["email"]
        session["role"] = user["role"]
        session["profile_pic"] = user["profile_pic"] or f"https://api.dicebear.com/7.x/initials/svg?seed={user['name']}"

        cursor.close()
        db.close()
        flash(f"Welcome back, {user['name']}!", "success")
        return redirect("/dashboard")

    return render_template("login.html")


@app.route("/login/demo/<role>")
def login_demo(role):
    """Direct 1-click instant login helper."""
    role = role.lower().strip()
    db = get_db()
    cursor = db.cursor(dictionary=True)

    if role == "admin":
        cursor.execute("SELECT * FROM users WHERE role = 'admin' LIMIT 1")
    elif role == "student":
        cursor.execute("SELECT * FROM users WHERE email = 'student@campus.com'")
        if not cursor.fetchone():
            cursor.execute("SELECT * FROM users WHERE role = 'student' LIMIT 1")
        else:
            cursor.execute("SELECT * FROM users WHERE email = 'student@campus.com'")
    elif role == "company":
        cursor.execute("SELECT * FROM users WHERE email = 'google@campus.com'")
        if not cursor.fetchone():
            cursor.execute("SELECT * FROM users WHERE role = 'company' LIMIT 1")
        else:
            cursor.execute("SELECT * FROM users WHERE email = 'google@campus.com'")
    else:
        cursor.execute("SELECT * FROM users WHERE role = %s LIMIT 1", (role,))

    user = cursor.fetchone()
    if user:
        session["user_id"] = user["id"]
        session["name"] = user["name"]
        session["email"] = user["email"]
        session["role"] = user["role"]
        session["profile_pic"] = user["profile_pic"] or f"https://api.dicebear.com/7.x/initials/svg?seed={user['name']}"
        cursor.close()
        db.close()
        flash(f"Logged in as {user['name']} ({user['role'].capitalize()}).", "success")
        return redirect("/dashboard")

    cursor.close()
    db.close()
    flash("Demo account not found.", "warning")
    return redirect("/login")


@app.route("/api/auth/send-otp", methods=["POST"])
def api_send_otp():
    """Validates Indian mobile number and sends/generates a 6-digit OTP via SMS service."""
    data = request.get_json(silent=True) or request.form
    phone = data.get("phone", "").strip()
    
    res = sms_service.request_otp(phone)
    if isinstance(res, tuple) and len(res) == 3:
        success, message, otp = res
    else:
        success, message = res[:2]
        otp = None

    if not success:
        return jsonify({"success": False, "message": message}), 400

    return jsonify({
        "success": True,
        "message": message,
        "otp": otp
    })


@app.route("/api/auth/verify-otp", methods=["POST"])
def api_verify_otp():
    """Verifies entered OTP against hashed storage and signs in or creates user."""
    data = request.get_json(silent=True) or request.form
    phone = data.get("phone", "").strip()
    otp = data.get("otp", "").strip()
    name = data.get("name", "").strip()

    success, message, clean_phone = sms_service.verify_otp_submission(phone, otp)
    if not success:
        return jsonify({"success": False, "message": message}), 400

    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE phone LIKE %s", (f"%{clean_phone[-10:]}",))
    user = cursor.fetchone()

    if not user:
        # Create a new user account if mobile number does not exist
        user_name = name if name else f"Student {clean_phone[-4:]}"
        user_email = f"{clean_phone[-10:]}@campus.com"
        
        cursor.execute("SELECT * FROM users WHERE email = %s", (user_email,))
        existing = cursor.fetchone()
        if existing:
            user = existing
        else:
            default_avatar = f"https://api.dicebear.com/7.x/initials/svg?seed={user_name}"
            cursor.execute("""
                INSERT INTO users (name, email, password, role, profile_pic, phone)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (user_name, user_email, "otp_authenticated_user", "student", default_avatar, clean_phone[-10:]))
            db.commit()
            user_id = cursor.lastrowid
            cursor.execute("INSERT INTO students (user_id, phone, skills) VALUES (%s, %s, %s)",
                           (user_id, clean_phone[-10:], "Campus Candidate"))
            db.commit()
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()

    # Populate authenticated session
    session["user_id"] = user["id"]
    session["name"] = user["name"]
    session["email"] = user["email"]
    session["role"] = user["role"]
    session["profile_pic"] = user["profile_pic"] or f"https://api.dicebear.com/7.x/initials/svg?seed={user['name']}"

    cursor.close()
    db.close()
    return jsonify({
        "success": True,
        "message": f"Welcome back, {user['name']}!",
        "redirect": "/dashboard"
    })


# -------------------------------------------------------------
# OFFICIAL GOOGLE OAUTH 2.0 / OPENID CONNECT (CONTINUE WITH GOOGLE)
# -------------------------------------------------------------

@app.route("/auth/google/login")
def google_login():
    """Initiates official Google OAuth 2.0 OpenID Connect authentication flow."""
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id or client_id.startswith("your_"):
        flash("Google OAuth credentials are not configured. Please set GOOGLE_CLIENT_ID in your .env file.", "warning")
        return redirect("/login")

    # Generate secure random state token for CSRF protection
    state = secrets.token_urlsafe(32)
    session["google_oauth_state"] = state

    # Determine redirect URI (Render / reverse proxy compatible)
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    if not redirect_uri:
        redirect_uri = url_for("google_callback", _external=True)
        if request.headers.get("X-Forwarded-Proto") == "https":
            redirect_uri = redirect_uri.replace("http://", "https://")

    session["google_redirect_uri"] = redirect_uri

    # Official Google OAuth 2.0 authorization URL
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "prompt": "select_account",  # Displays Google account chooser / detects signed-in accounts
        "state": state
    }
    google_auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    return redirect(google_auth_url)


@app.route("/auth/google/callback")
def google_callback():
    """Handles callback from Google OAuth server after user selects account."""
    # 1. Validate state parameter to prevent CSRF attacks
    state = request.args.get("state")
    saved_state = session.pop("google_oauth_state", None)
    if not state or state != saved_state:
        flash("Google authentication error: session state mismatch or expired. Please try again.", "danger")
        return redirect("/login")

    # 2. Check for Google error response (e.g. user canceled consent)
    error = request.args.get("error")
    if error:
        flash(f"Google sign-in was canceled or encountered an error: {error}", "warning")
        return redirect("/login")

    # 3. Retrieve authorization code
    code = request.args.get("code")
    if not code:
        flash("Google authentication failed: no authorization code returned.", "danger")
        return redirect("/login")

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    redirect_uri = session.pop("google_redirect_uri", None) or url_for("google_callback", _external=True)

    # 4. Exchange authorization code for tokens securely on server
    token_url = "https://oauth2.googleapis.com/token"
    token_payload = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }

    try:
        token_resp = requests.post(token_url, data=token_payload, timeout=10)
        token_data = token_resp.json()
    except Exception as e:
        flash(f"Failed to connect to Google OAuth server: {str(e)}", "danger")
        return redirect("/login")

    access_token = token_data.get("access_token")
    if not access_token:
        err_msg = token_data.get("error_description", token_data.get("error", "Unable to retrieve Google access token."))
        flash(f"Google login failed: {err_msg}", "danger")
        return redirect("/login")

    # 5. Fetch verified user profile from OpenID Connect userinfo endpoint
    try:
        userinfo_resp = requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10
        )
        userinfo = userinfo_resp.json()
    except Exception as e:
        flash(f"Failed to retrieve user profile from Google: {str(e)}", "danger")
        return redirect("/login")

    email = userinfo.get("email", "").strip().lower()
    name = userinfo.get("name", "").strip() or email.split("@")[0].title()
    picture = userinfo.get("picture", "")

    if not email:
        flash("Google account did not return a valid email address.", "danger")
        return redirect("/login")

    # 6. Check if user already exists in database
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE LOWER(email) = %s", (email,))
    user = cursor.fetchone()

    if not user:
        # Create new user for this Google account
        avatar_url = picture if picture else f"https://api.dicebear.com/7.x/initials/svg?seed={name}"
        cursor.execute("""
            INSERT INTO users (name, email, password, role, profile_pic)
            VALUES (%s, %s, %s, %s, %s)
        """, (name, email, "google_oauth_auth", "student", avatar_url))
        db.commit()
        user_id = cursor.lastrowid
        cursor.execute("INSERT INTO students (user_id, skills) VALUES (%s, %s)", (user_id, "Google Authenticated Student"))
        db.commit()
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
    else:
        # If user exists and profile picture is empty, update with Google picture
        if picture and not user.get("profile_pic"):
            cursor.execute("UPDATE users SET profile_pic = %s WHERE id = %s", (picture, user["id"]))
            db.commit()
            user["profile_pic"] = picture

    # 7. Authenticate user session
    session["user_id"] = user["id"]
    session["name"] = user["name"]
    session["email"] = user["email"]
    session["role"] = user["role"]
    session["profile_pic"] = user["profile_pic"] or f"https://api.dicebear.com/7.x/initials/svg?seed={user['name']}"

    cursor.close()
    db.close()
    flash(f"Welcome, {user['name']}! Signed in via Google.", "success")
    return redirect("/dashboard")


@app.route("/api/auth/forgot-password", methods=["POST"])
def api_forgot_password():
    """Handles password reset request with OTP verification."""
    data = request.get_json(silent=True) or request.form
    step = data.get("step", "request_otp")
    identifier = data.get("identifier", "").strip().lower()
    otp = data.get("otp", "").strip()
    new_password = data.get("new_password", "").strip()

    db = get_db()
    cursor = db.cursor(dictionary=True)

    if step == "request_otp":
        if not identifier:
            cursor.close()
            db.close()
            return jsonify({"success": False, "message": "Please enter your registered email or phone number."}), 400

        cursor.execute("SELECT * FROM users WHERE LOWER(email) = %s OR phone LIKE %s", (identifier, f"%{identifier[-10:]}"))
        user = cursor.fetchone()
        if not user:
            cursor.close()
            db.close()
            return jsonify({"success": False, "message": "No registered account found with that email or phone."}), 404

        gen_otp = str(random.randint(100000, 999999))
        session["reset_otp"] = gen_otp
        session["reset_user_id"] = user["id"]
        cursor.close()
        db.close()
        return jsonify({
            "success": True,
            "message": f"Reset code sent to {user['email']}!",
            "otp": gen_otp
        })

    elif step == "reset":
        expected_otp = session.get("reset_otp")
        user_id = session.get("reset_user_id")
        if not expected_otp or str(otp) != str(expected_otp) or not user_id:
            cursor.close()
            db.close()
            return jsonify({"success": False, "message": "Invalid or expired reset code. Please request a new one."}), 400

        if not new_password or len(new_password) < 4:
            cursor.close()
            db.close()
            return jsonify({"success": False, "message": "Password must be at least 4 characters long."}), 400

        cursor.execute("UPDATE users SET password = %s WHERE id = %s", (new_password, user_id))
        db.commit()
        session.pop("reset_otp", None)
        session.pop("reset_user_id", None)
        cursor.close()
        db.close()
        return jsonify({"success": True, "message": "Password reset successfully! Please sign in with your new password."})

    cursor.close()
    db.close()
    return jsonify({"success": False, "message": "Invalid request."}), 400


@app.route("/api/user-avatar")
def api_user_avatar():
    """Look up a user's avatar by email to show interactive preview on the login page."""
    email = request.args.get("email", "").strip().lower()
    if not email:
        return jsonify({"avatar": None})

    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT profile_pic FROM users WHERE LOWER(email) = %s", (email,))
    row = cursor.fetchone()
    cursor.close()
    db.close()

    if row and row.get("profile_pic"):
        return jsonify({"avatar": row["profile_pic"]})
    return jsonify({"avatar": None})


# -------------------------------------------------------------
# DASHBOARD
# -------------------------------------------------------------

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        flash("Please log in to access your dashboard.", "info")
        return redirect("/login")

    role = session["role"]
    db = get_db()
    cursor = db.cursor(dictionary=True)

    # 1. ADMIN DASHBOARD
    if role == "admin":
        cursor.execute("SELECT COUNT(*) AS total FROM users")
        users = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM students")
        students = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM companies")
        companies = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM jobs")
        jobs = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM applications")
        applications = cursor.fetchone()["total"]

        # Fetch detailed tables for admin portal management
        cursor.execute("""
            SELECT jobs.*, companies.company_name, COUNT(applications.id) AS applicant_count
            FROM jobs
            JOIN companies ON jobs.company_id = companies.id
            LEFT JOIN applications ON jobs.id = applications.job_id
            GROUP BY jobs.id
            ORDER BY jobs.created_at DESC
        """)
        admin_jobs = cursor.fetchall()

        cursor.execute("""
            SELECT students.*, users.name, users.email, users.profile_pic,
                   COUNT(applications.id) AS apps_count
            FROM students
            JOIN users ON students.user_id = users.id
            LEFT JOIN applications ON students.id = applications.student_id
            GROUP BY students.id
            ORDER BY students.cgpa DESC
        """)
        admin_students = cursor.fetchall()

        cursor.execute("""
            SELECT companies.*, users.name AS recruiter_name, users.email,
                   COUNT(jobs.id) AS drives_count
            FROM companies
            JOIN users ON companies.user_id = users.id
            LEFT JOIN jobs ON companies.id = jobs.company_id
            GROUP BY companies.id
            ORDER BY drives_count DESC
        """)
        admin_companies = cursor.fetchall()

        cursor.execute("""
            SELECT applications.*, users.name AS student_name, users.email AS student_email,
                   students.roll_no, students.branch, students.cgpa,
                   jobs.title AS job_title, companies.company_name
            FROM applications
            JOIN students ON applications.student_id = students.id
            JOIN users ON students.user_id = users.id
            JOIN jobs ON applications.job_id = jobs.id
            JOIN companies ON jobs.company_id = companies.id
            ORDER BY applications.applied_at DESC
            LIMIT 25
        """)
        admin_applications = cursor.fetchall()

        cursor.close()
        db.close()
        return render_template(
            "dashboard.html",
            users=users,
            students=students,
            companies=companies,
            jobs=jobs,
            applications=applications,
            admin_jobs=admin_jobs,
            admin_students=admin_students,
            admin_companies=admin_companies,
            admin_applications=admin_applications
        )

    # 2. STUDENT DASHBOARD
    elif role == "student":
        cursor.execute("""
            SELECT students.*, users.name, users.email, users.profile_pic
            FROM students
            JOIN users ON students.user_id = users.id
            WHERE students.user_id = %s
        """, (session["user_id"],))
        student = cursor.fetchone()

        # Fallback if student record wasn't created
        if not student:
            cursor.execute("INSERT INTO students (user_id) VALUES (%s)", (session["user_id"],))
            db.commit()
            cursor.execute("SELECT * FROM students WHERE user_id = %s", (session["user_id"],))
            student = cursor.fetchone()

        cursor.execute("""
            SELECT applications.*, jobs.title, jobs.salary, jobs.location, companies.company_name
            FROM applications
            JOIN jobs ON applications.job_id = jobs.id
            JOIN companies ON jobs.company_id = companies.id
            WHERE applications.student_id = %s
            ORDER BY applications.applied_at DESC
        """, (student["id"],))
        applications = cursor.fetchall()

        cursor.close()
        db.close()
        return render_template("dashboard.html", student=student, applications=applications)

    # 3. RECRUITER / COMPANY DASHBOARD
    else:
        cursor.execute("SELECT * FROM companies WHERE user_id = %s", (session["user_id"],))
        company = cursor.fetchone()

        # Fallback create company row if needed
        if not company:
            cursor.execute("INSERT INTO companies (user_id, company_name) VALUES (%s, %s)", (session["user_id"], session["name"]))
            db.commit()
            cursor.execute("SELECT * FROM companies WHERE user_id = %s", (session["user_id"],))
            company = cursor.fetchone()

        cursor.execute("""
            SELECT jobs.*, COUNT(applications.id) AS applicant_count
            FROM jobs
            LEFT JOIN applications ON jobs.id = applications.job_id
            WHERE jobs.company_id = %s
            GROUP BY jobs.id
            ORDER BY jobs.created_at DESC
        """, (company["id"],))
        jobs = cursor.fetchall()

        cursor.close()
        db.close()
        return render_template("dashboard.html", company=company, jobs=jobs)


# -------------------------------------------------------------
# POST JOB / RECRUITMENT DRIVE
# -------------------------------------------------------------

@app.route("/post-job", methods=["GET", "POST"])
def post_job():
    if "user_id" not in session:
        return redirect("/login")
    if session.get("role") != "company":
        flash("Only company recruiters can post recruitment drives.", "warning")
        return redirect("/dashboard")

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT id FROM companies WHERE user_id = %s", (session["user_id"],))
    company = cursor.fetchone()
    if not company:
        cursor.execute("INSERT INTO companies (user_id, company_name) VALUES (%s, %s)", (session["user_id"], session["name"]))
        db.commit()
        company = {"id": cursor.lastrowid}

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        eligibility = request.form.get("eligibility", "").strip()
        salary = request.form.get("salary", "").strip()
        location = request.form.get("location", "").strip()
        job_type = request.form.get("job_type", "Full Time")
        skills = request.form.get("skills", "").strip()
        deadline = request.form.get("deadline", "").strip()

        cursor.execute("""
            INSERT INTO jobs (company_id, title, description, eligibility, salary, location, job_type, skills, deadline)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (company["id"], title, description, eligibility, salary, location, job_type, skills, deadline))
        db.commit()

        cursor.close()
        db.close()
        flash("Recruitment drive posted successfully!", "success")
        return redirect("/dashboard")

    cursor.close()
    db.close()
    return render_template("post_job.html")


# -------------------------------------------------------------
# APPLY FOR DRIVE
# -------------------------------------------------------------

@app.route("/apply/<int:job_id>")
def apply(job_id):
    if "user_id" not in session:
        flash("Please log in as a student to apply for recruitment drives.", "info")
        return redirect("/login")

    if session.get("role") != "student":
        flash("Only student accounts can apply for recruitment drives.", "warning")
        return redirect(f"/job/{job_id}")

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT id FROM students WHERE user_id = %s", (session["user_id"],))
    student = cursor.fetchone()
    if not student:
        cursor.execute("INSERT INTO students (user_id) VALUES (%s)", (session["user_id"],))
        db.commit()
        student = {"id": cursor.lastrowid}

    # Check if already applied
    cursor.execute("SELECT id FROM applications WHERE job_id = %s AND student_id = %s", (job_id, student["id"]))
    if cursor.fetchone():
        cursor.close()
        db.close()
        flash("You have already submitted an application for this drive.", "info")
        return redirect("/dashboard")

    try:
        cursor.execute("""
            INSERT INTO applications (job_id, student_id, status)
            VALUES (%s, %s, 'Applied')
        """, (job_id, student["id"]))
        db.commit()
        flash("Application submitted successfully! Track your status on your dashboard.", "success")
    except Exception as e:
        db.rollback()
        flash(f"Application failed: {str(e)}", "danger")

    cursor.close()
    db.close()
    return redirect("/dashboard")


# -------------------------------------------------------------
# RECRUITER: REVIEW APPLICANTS & UPDATE STATUS
# -------------------------------------------------------------

@app.route("/applicants/<int:job_id>")
def applicants(job_id):
    if "user_id" not in session:
        return redirect("/login")
    if session.get("role") != "company":
        flash("Access restricted to recruiting companies.", "danger")
        return redirect("/dashboard")

    db = get_db()
    cursor = db.cursor(dictionary=True)

    # Verify drive belongs to current company
    cursor.execute("""
        SELECT jobs.*, companies.id AS comp_id
        FROM jobs
        JOIN companies ON jobs.company_id = companies.id
        WHERE jobs.id = %s AND companies.user_id = %s
    """, (job_id, session["user_id"]))
    job = cursor.fetchone()

    if not job and session.get("role") != "admin":
        cursor.close()
        db.close()
        flash("Unauthorized or recruitment drive not found.", "danger")
        return redirect("/dashboard")

    # Fetch applicants with candidate details, profile pic, resume
    cursor.execute("""
        SELECT applications.id, applications.status, applications.applied_at,
               users.name, users.email, users.profile_pic,
               students.roll_no, students.branch, students.year, students.cgpa, students.phone, students.resume
        FROM applications
        JOIN students ON applications.student_id = students.id
        JOIN users ON students.user_id = users.id
        WHERE applications.job_id = %s
        ORDER BY applications.applied_at DESC
    """, (job_id,))
    applicant_list = cursor.fetchall()

    cursor.close()
    db.close()
    return render_template("applicants.html", applicants=applicant_list, job=job)


@app.route("/update-status/<int:application_id>/<status>")
def update_status(application_id, status):
    if "user_id" not in session or session.get("role") not in ["company", "admin"]:
        return redirect("/login")

    allowed_statuses = ["Applied", "Shortlisted", "Rejected", "Selected"]
    if status not in allowed_statuses:
        flash("Invalid status transition.", "warning")
        return redirect("/dashboard")

    db = get_db()
    cursor = db.cursor()

    cursor.execute("UPDATE applications SET status = %s WHERE id = %s", (status, application_id))
    db.commit()
    cursor.close()
    db.close()

    flash(f"Application status updated to '{status}' successfully.", "success")
    return redirect(request.referrer or "/dashboard")


# -------------------------------------------------------------
# USER PROFILE & SETTINGS
# -------------------------------------------------------------

@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user_id" not in session:
        return redirect("/login")

    db = get_db()
    cursor = db.cursor(dictionary=True)

    user_id = session["user_id"]
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()

    student = None
    company = None
    if user["role"] == "student":
        cursor.execute("SELECT * FROM students WHERE user_id = %s", (user_id,))
        student = cursor.fetchone()
    elif user["role"] == "company":
        cursor.execute("SELECT * FROM companies WHERE user_id = %s", (user_id,))
        company = cursor.fetchone()

    if request.method == "POST":
        name = request.form.get("name", user["name"]).strip()
        new_password = request.form.get("new_password", "").strip()

        # Handle Profile Picture
        profile_pic = user["profile_pic"]
        if "profile_picture" in request.files:
            uploaded_pic = save_file(request.files["profile_picture"], AVATARS_FOLDER, ALLOWED_IMAGE_EXTENSIONS)
            if uploaded_pic:
                profile_pic = uploaded_pic

        preset = request.form.get("preset_avatar", "").strip()
        if preset:
            profile_pic = preset

        # Update Users table
        if new_password:
            cursor.execute("""
                UPDATE users SET name = %s, password = %s, profile_pic = %s WHERE id = %s
            """, (name, new_password, profile_pic, user_id))
        else:
            cursor.execute("""
                UPDATE users SET name = %s, profile_pic = %s WHERE id = %s
            """, (name, profile_pic, user_id))

        session["name"] = name
        session["profile_pic"] = profile_pic

        # Role specific updates
        if user["role"] == "student":
            resume_url = student["resume"] if student else ""
            if "resume_file" in request.files:
                uploaded_resume = save_file(request.files["resume_file"], RESUMES_FOLDER, ALLOWED_DOC_EXTENSIONS)
                if uploaded_resume:
                    resume_url = uploaded_resume

            cursor.execute("""
                UPDATE students
                SET roll_no = %s, branch = %s, year = %s, cgpa = %s, phone = %s, skills = %s, bio = %s, resume = %s
                WHERE user_id = %s
            """, (
                request.form.get("roll_no", ""),
                request.form.get("branch", ""),
                request.form.get("year", ""),
                float(request.form.get("cgpa") or 0.0),
                request.form.get("phone", ""),
                request.form.get("skills", ""),
                request.form.get("bio", ""),
                resume_url,
                user_id
            ))

        elif user["role"] == "company":
            cursor.execute("""
                UPDATE companies
                SET company_name = %s, website = %s, location = %s, logo = %s, description = %s
                WHERE user_id = %s
            """, (
                request.form.get("company_name", ""),
                request.form.get("website", ""),
                request.form.get("location", ""),
                request.form.get("logo", ""),
                request.form.get("description", ""),
                user_id
            ))

        db.commit()
        cursor.close()
        db.close()
        flash("Profile updated successfully!", "success")
        return redirect("/profile")

    cursor.close()
    db.close()
    return render_template("profile.html", user=user, student=student, company=company)


# -------------------------------------------------------------
# LOGOUT & ERROR HANDLERS
# -------------------------------------------------------------

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "info")
    return redirect("/")


@app.route("/favicon.ico")
def favicon():
    """Silence browser favicon requests."""
    return "", 200, {"Content-Type": "image/x-icon"}


@app.errorhandler(404)
def page_not_found(e):
    return redirect(url_for("index"))


@app.errorhandler(500)
def internal_server_error(e):
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1", port=5000)