import os
import sqlite3

# Try importing mysql.connector if installed
try:
    import mysql.connector
    HAS_MYSQL = True
except ImportError:
    HAS_MYSQL = False

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "campus_recruitment.db")


class SQLiteCursorWrapper:
    """Wraps sqlite3.Cursor to provide a MySQL-compatible interface (e.g. %s placeholders, dict results, lastrowid)."""
    def __init__(self, cursor):
        self.cursor = cursor
        self.description = cursor.description

    def execute(self, query, params=None):
        # Convert %s placeholders to ? placeholders for SQLite
        query = query.replace("%s", "?")
        if params is not None:
            if isinstance(params, (list, tuple)):
                clean_params = tuple(None if p is None else p for p in params)
                res = self.cursor.execute(query, clean_params)
            else:
                res = self.cursor.execute(query, (params,))
        else:
            res = self.cursor.execute(query)
        self.description = self.cursor.description
        return res

    def fetchone(self):
        row = self.cursor.fetchone()
        if row is None:
            return None
        if isinstance(row, sqlite3.Row):
            return dict(row)
        if self.description:
            cols = [col[0] for col in self.description]
            return dict(zip(cols, row))
        return row

    def fetchall(self):
        rows = self.cursor.fetchall()
        if not rows:
            return []
        if isinstance(rows[0], sqlite3.Row):
            return [dict(r) for r in rows]
        if self.description:
            cols = [col[0] for col in self.description]
            return [dict(zip(cols, r)) for r in rows]
        return rows

    @property
    def lastrowid(self):
        return self.cursor.lastrowid

    @property
    def rowcount(self):
        return self.cursor.rowcount

    def close(self):
        self.cursor.close()


class SQLiteConnectionWrapper:
    """Wraps sqlite3.Connection to allow cursor(dictionary=True) and standard methods."""
    def __init__(self, conn):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    def cursor(self, dictionary=True):
        return SQLiteCursorWrapper(self.conn.cursor())

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()


USE_MYSQL = os.environ.get("DB_ENGINE", "").lower() == "mysql" or os.environ.get("USE_MYSQL", "").lower() in ("true", "1")

def get_db():
    """Returns a database connection. Uses SQLite by default; uses MySQL only if explicitly configured."""
    if USE_MYSQL and HAS_MYSQL:
        try:
            conn = mysql.connector.connect(
                host=os.environ.get("MYSQL_HOST", "localhost"),
                user=os.environ.get("MYSQL_USER", "root"),
                password=os.environ.get("MYSQL_PASSWORD", ""),
                database=os.environ.get("MYSQL_DB", "campus_recruitment"),
                connection_timeout=2
            )
            return conn
        except Exception:
            pass  # Fall back to SQLite

    # SQLite primary reliable database
    conn = sqlite3.connect(DB_FILE, timeout=10)
    return SQLiteConnectionWrapper(conn)


def init_db(force_reseed=False):
    """Initialize database tables and seed comprehensive sample data."""
    db = get_db()
    cursor = db.cursor(dictionary=True)

    is_sqlite = isinstance(db, SQLiteConnectionWrapper)
    auto_inc = "AUTOINCREMENT" if is_sqlite else "AUTO_INCREMENT"
    text_type = "TEXT" if is_sqlite else "VARCHAR(255)"

    # Create tables
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY {auto_inc},
            name {text_type} NOT NULL,
            email {text_type} UNIQUE NOT NULL,
            password {text_type} NOT NULL,
            role {text_type} NOT NULL,
            phone {text_type} DEFAULT '',
            profile_pic {text_type} DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY {auto_inc},
            user_id INTEGER NOT NULL,
            roll_no {text_type},
            branch {text_type},
            year {text_type},
            cgpa REAL DEFAULT 0,
            phone {text_type},
            resume {text_type} DEFAULT '',
            skills {text_type} DEFAULT '',
            bio {text_type} DEFAULT '',
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY {auto_inc},
            user_id INTEGER NOT NULL,
            company_name {text_type},
            website {text_type},
            location {text_type},
            logo {text_type} DEFAULT '',
            description TEXT DEFAULT '',
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY {auto_inc},
            company_id INTEGER NOT NULL,
            title {text_type} NOT NULL,
            description TEXT,
            eligibility {text_type},
            salary {text_type},
            location {text_type},
            job_type {text_type} DEFAULT 'Full Time',
            skills {text_type} DEFAULT '',
            deadline {text_type},
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_id) REFERENCES companies(id)
        )
    """)

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY {auto_inc},
            job_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            status {text_type} DEFAULT 'Applied',
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notes {text_type} DEFAULT '',
            FOREIGN KEY (job_id) REFERENCES jobs(id),
            FOREIGN KEY (student_id) REFERENCES students(id)
        )
    """)
    db.commit()

    # Check if jobs need to be seeded or expanded
    cursor.execute("SELECT COUNT(*) AS total_jobs FROM jobs")
    count_res = cursor.fetchone()
    total_jobs = count_res["total_jobs"] if isinstance(count_res, dict) else count_res[0]

    if total_jobs < 10 or force_reseed:
        seed_sample_data(db)

    cursor.close()
    db.close()


def reset_database():
    """Completely resets all tables, deleting custom test data and reseeding default seed data."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    tables = ["applications", "jobs", "students", "companies", "users"]
    for t in tables:
        try:
            cursor.execute(f"DROP TABLE IF EXISTS {t}")
        except Exception:
            pass
    db.commit()
    cursor.close()
    db.close()
    init_db(force_reseed=True)


def seed_sample_data(db):
    """Seed comprehensive list of 20+ companies, recruitment drives, students, and admin."""
    cursor = db.cursor(dictionary=True)

    # 1. Admin Account
    cursor.execute("SELECT id FROM users WHERE email = 'admin@campus.com'")
    admin_user = cursor.fetchone()
    if not admin_user:
        cursor.execute("""
            INSERT INTO users (name, email, password, role, profile_pic)
            VALUES (%s, %s, %s, %s, %s)
        """, ("System Administrator", "admin@campus.com", "admin123", "admin", "https://api.dicebear.com/7.x/bottts/svg?seed=admin"))
    else:
        cursor.execute("""
            UPDATE users 
            SET name = %s, password = %s, role = %s, profile_pic = %s
            WHERE email = 'admin@campus.com'
        """, ("System Administrator", "admin123", "admin", "https://api.dicebear.com/7.x/bottts/svg?seed=admin"))

    # 2. Comprehensive Global & Domestic Recruiting Partners
    sample_companies = [
        {
            "name": "Google Campus Hiring",
            "email": "google@campus.com",
            "password": "recruiter123",
            "company_name": "Google",
            "website": "https://careers.google.com",
            "location": "Bangalore & Hyderabad",
            "logo": "https://cdn.jsdelivr.net/gh/devicons/devicon/icons/google/google-original.svg",
            "description": "Google LLC is an American multinational technology company focusing on artificial intelligence, search engine technology, cloud computing, and computer software."
        },
        {
            "name": "Microsoft University Talent",
            "email": "microsoft@campus.com",
            "password": "recruiter123",
            "company_name": "Microsoft",
            "website": "https://careers.microsoft.com",
            "location": "Hyderabad, Bangalore & Noida",
            "logo": "https://cdn.jsdelivr.net/gh/devicons/devicon/icons/azure/azure-original.svg",
            "description": "Microsoft Corporation produces computer software, consumer electronics, personal computers, Azure cloud services, and enterprise AI."
        },
        {
            "name": "Amazon Campus Recruiting",
            "email": "amazon@campus.com",
            "password": "recruiter123",
            "company_name": "Amazon",
            "website": "https://amazon.jobs",
            "location": "Hyderabad, Bangalore & Chennai",
            "logo": "https://cdn.jsdelivr.net/gh/devicons/devicon/icons/amazonwebservices/amazonwebservices-original-wordmark.svg",
            "description": "Amazon is a global leader in e-commerce, cloud computing (AWS), digital streaming, and artificial intelligence solutions."
        },
        {
            "name": "Apple India University Relations",
            "email": "apple@campus.com",
            "password": "recruiter123",
            "company_name": "Apple",
            "website": "https://www.apple.com/careers/in/",
            "location": "Hyderabad & Bangalore",
            "logo": "https://cdn.jsdelivr.net/gh/devicons/devicon/icons/apple/apple-original.svg",
            "description": "Apple Inc. designs, manufactures, and markets smartphones, personal computers, tablets, wearables, and accessories, along with world-class operating systems."
        },
        {
            "name": "Goldman Sachs Campus Talent",
            "email": "goldman@campus.com",
            "password": "recruiter123",
            "company_name": "Goldman Sachs",
            "website": "https://goldmansachs.com/careers",
            "location": "Bangalore & Hyderabad",
            "logo": "https://images.unsplash.com/photo-1554224155-8d04cb21cd6c?w=100&auto=format&fit=crop&q=80",
            "description": "The Goldman Sachs Group, Inc. is a leading global financial institution that delivers a broad range of financial services to a large and diversified client base."
        },
        {
            "name": "Adobe Campus Programs",
            "email": "adobe@campus.com",
            "password": "recruiter123",
            "company_name": "Adobe",
            "website": "https://www.adobe.com/careers.html",
            "location": "Noida & Bangalore",
            "logo": "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=100&auto=format&fit=crop&q=80",
            "description": "Adobe is an American multinational computer software company focused on digital media, creativity tools, and document management applications."
        },
        {
            "name": "Salesforce University Recruiting",
            "email": "salesforce@campus.com",
            "password": "recruiter123",
            "company_name": "Salesforce",
            "website": "https://www.salesforce.com/company/careers/",
            "location": "Hyderabad & Bangalore",
            "logo": "https://images.unsplash.com/photo-1551836022-d5d88e9218df?w=100&auto=format&fit=crop&q=80",
            "description": "Salesforce, Inc. is the world leader in Customer Relationship Management (CRM) and cloud application platforms."
        },
        {
            "name": "Oracle Campus Hiring",
            "email": "oracle@campus.com",
            "password": "recruiter123",
            "company_name": "Oracle",
            "website": "https://www.oracle.com/corporate/careers/",
            "location": "Bangalore & Hyderabad",
            "logo": "https://cdn.jsdelivr.net/gh/devicons/devicon/icons/oracle/oracle-original.svg",
            "description": "Oracle Corporation offers enterprise cloud infrastructure, autonomous databases, and enterprise resource planning software."
        },
        {
            "name": "Cisco University Relations",
            "email": "cisco@campus.com",
            "password": "recruiter123",
            "company_name": "Cisco Systems",
            "website": "https://www.cisco.com/c/en/us/about/careers.html",
            "location": "Bangalore",
            "logo": "https://images.unsplash.com/photo-1544197150-b99a580bb7a8?w=100&auto=format&fit=crop&q=80",
            "description": "Cisco Systems, Inc. is an American multinational digital communications technology conglomerate corporation specializing in networking and cybersecurity."
        },
        {
            "name": "Uber University Talent",
            "email": "uber@campus.com",
            "password": "recruiter123",
            "company_name": "Uber Technologies",
            "website": "https://www.uber.com/us/en/careers/",
            "location": "Bangalore & Hyderabad",
            "logo": "https://images.unsplash.com/photo-1557804506-669a67965ba0?w=100&auto=format&fit=crop&q=80",
            "description": "Uber Technologies operates mobility platforms, food delivery, and freight networks with cutting-edge real-time geospatial computing."
        },
        {
            "name": "Qualcomm Campus Talent",
            "email": "qualcomm@campus.com",
            "password": "recruiter123",
            "company_name": "Qualcomm",
            "website": "https://www.qualcomm.com/company/careers",
            "location": "Hyderabad, Bangalore & Chennai",
            "logo": "https://images.unsplash.com/photo-1518770660439-4636190af475?w=100&auto=format&fit=crop&q=80",
            "description": "Qualcomm is an American multinational corporation focused on wireless telecommunications, 5G chipsets, and AI computing hardware."
        },
        {
            "name": "Morgan Stanley Campus Hiring",
            "email": "morgan@campus.com",
            "password": "recruiter123",
            "company_name": "Morgan Stanley",
            "website": "https://www.morganstanley.com/people/student-and-graduates",
            "location": "Mumbai & Bangalore",
            "logo": "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?w=100&auto=format&fit=crop&q=80",
            "description": "Morgan Stanley is a multinational investment bank and financial services company engineering high-frequency trading platforms and financial systems."
        },
        {
            "name": "Intel University Program",
            "email": "intel@campus.com",
            "password": "recruiter123",
            "company_name": "Intel Corporation",
            "website": "https://www.intel.com/content/www/us/en/jobs/jobs-at-intel.html",
            "location": "Bangalore",
            "logo": "https://images.unsplash.com/photo-1518770660439-4636190af475?w=100&auto=format&fit=crop&q=80",
            "description": "Intel Corporation is an American multinational corporation and technology company developing central processing units, microprocessors, and AI accelerators."
        },
        {
            "name": "Flipkart Campus Recruiting",
            "email": "flipkart@campus.com",
            "password": "recruiter123",
            "company_name": "Flipkart",
            "website": "https://www.flipkartcareers.com/",
            "location": "Bangalore",
            "logo": "https://images.unsplash.com/photo-1526304640581-d334cdbbf45e?w=100&auto=format&fit=crop&q=80",
            "description": "Flipkart is India's premier e-commerce marketplace pioneering high-throughput supply chain technology, payments, and distributed catalog engines."
        },
        {
            "name": "Atlassian University Relations",
            "email": "atlassian@campus.com",
            "password": "recruiter123",
            "company_name": "Atlassian",
            "website": "https://www.atlassian.com/company/careers",
            "location": "Remote & Bangalore",
            "logo": "https://images.unsplash.com/photo-1498050108023-c5249f4df085?w=100&auto=format&fit=crop&q=80",
            "description": "Atlassian is an Australian-American software company that develops products for software developers, project managers, including Jira and Confluence."
        },
        {
            "name": "Netflix University Hiring",
            "email": "netflix@campus.com",
            "password": "recruiter123",
            "company_name": "Netflix",
            "website": "https://jobs.netflix.com/",
            "location": "Mumbai & Remote",
            "logo": "https://images.unsplash.com/photo-1574375927938-d5a98e8ffe85?w=100&auto=format&fit=crop&q=80",
            "description": "Netflix is a global streaming service and production company known for ultra-scalable microservices architecture and video encoding."
        },
        {
            "name": "TCS Talent Acquisition",
            "email": "tcs@campus.com",
            "password": "recruiter123",
            "company_name": "Tata Consultancy Services (TCS)",
            "website": "https://tcs.com/careers",
            "location": "Pune, Mumbai & Hyderabad",
            "logo": "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?w=100&auto=format&fit=crop&q=80",
            "description": "TCS is an Indian multinational information technology services and consulting company driving digital transformation."
        },
        {
            "name": "Infosys Recruitment Cell",
            "email": "infosys@campus.com",
            "password": "recruiter123",
            "company_name": "Infosys",
            "website": "https://infosys.com/careers",
            "location": "Bangalore & Mysore",
            "logo": "https://images.unsplash.com/photo-1497366216548-37526070297c?w=100&auto=format&fit=crop&q=80",
            "description": "Infosys is a global leader in next-generation digital services, enterprise cloud migration, and AI consulting."
        },
        {
            "name": "IBM India University Hiring",
            "email": "ibm@campus.com",
            "password": "recruiter123",
            "company_name": "IBM India",
            "website": "https://www.ibm.com/in-en/employment/",
            "location": "Bangalore & Pune",
            "logo": "https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=100&auto=format&fit=crop&q=80",
            "description": "IBM is a global technology and innovation leader delivering hybrid cloud, artificial intelligence (watsonx), and quantum computing solutions."
        },
        {
            "name": "Wipro Campus Careers",
            "email": "wipro@campus.com",
            "password": "recruiter123",
            "company_name": "Wipro Technologies",
            "website": "https://careers.wipro.com/",
            "location": "Bangalore & Hyderabad",
            "logo": "https://images.unsplash.com/photo-1504384308090-c894fdcc538d?w=100&auto=format&fit=crop&q=80",
            "description": "Wipro Limited is a leading technology services and consulting company focused on building innovative solutions addressing clients' most complex digital transformation needs."
        }
    ]

    company_id_map = {}
    for c in sample_companies:
        cursor.execute("SELECT id FROM users WHERE email = %s", (c["email"],))
        existing_user = cursor.fetchone()
        if existing_user:
            uid = existing_user["id"]
        else:
            cursor.execute("""
                INSERT INTO users (name, email, password, role, profile_pic)
                VALUES (%s, %s, %s, %s, %s)
            """, (c["name"], c["email"], c["password"], "company", f"https://api.dicebear.com/7.x/initials/svg?seed={c['company_name']}"))
            uid = cursor.lastrowid

        cursor.execute("SELECT id FROM companies WHERE user_id = %s", (uid,))
        existing_comp = cursor.fetchone()
        if existing_comp:
            cid = existing_comp["id"]
        else:
            cursor.execute("""
                INSERT INTO companies (user_id, company_name, website, location, logo, description)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (uid, c["company_name"], c["website"], c["location"], c["logo"], c["description"]))
            cid = cursor.lastrowid
        company_id_map[c["company_name"]] = cid

    # 3. Comprehensive Sample Students
    sample_students = [
        {
            "name": "Rahul Sharma",
            "email": "student@campus.com",
            "password": "student123",
            "roll_no": "2022CSE104",
            "branch": "Computer Science & Engineering",
            "year": "4th Year (2026)",
            "cgpa": 8.85,
            "phone": "+91 98765 43210",
            "skills": "Python, React, Flask, PostgreSQL, Docker, Data Structures",
            "bio": "Passionate full-stack developer with experience in microservices and algorithmic problem solving.",
            "profile_pic": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150&auto=format&fit=crop&q=80"
        },
        {
            "name": "Priya Patel",
            "email": "priya@campus.com",
            "password": "student123",
            "roll_no": "2022IT045",
            "branch": "Information Technology",
            "year": "4th Year (2026)",
            "cgpa": 9.20,
            "phone": "+91 98123 45678",
            "skills": "Java, Spring Boot, AWS, Kubernetes, Machine Learning",
            "bio": "Dean's lister, cloud enthusiast, and open-source contributor.",
            "profile_pic": "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=150&auto=format&fit=crop&q=80"
        },
        {
            "name": "Amit Kumar",
            "email": "amit@campus.com",
            "password": "student123",
            "roll_no": "2022ECE082",
            "branch": "Electronics & Communication",
            "year": "4th Year (2026)",
            "cgpa": 8.10,
            "phone": "+91 97654 32109",
            "skills": "C++, Embedded Systems, Linux, IoT, Python",
            "bio": "Hardware-software co-design enthusiast with high proficiency in C++ and systems programming.",
            "profile_pic": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=150&auto=format&fit=crop&q=80"
        },
        {
            "name": "Sneha Reddy",
            "email": "sneha@campus.com",
            "password": "student123",
            "roll_no": "2022AIML018",
            "branch": "Artificial Intelligence & Data Science",
            "year": "4th Year (2026)",
            "cgpa": 9.40,
            "phone": "+91 98888 77777",
            "skills": "PyTorch, TensorFlow, Deep Learning, NLP, Python, SQL",
            "bio": "AI research fellow focused on Large Language Models, Generative AI, and computer vision algorithms.",
            "profile_pic": "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=150&auto=format&fit=crop&q=80"
        },
        {
            "name": "Rohan Gupta",
            "email": "rohan@campus.com",
            "password": "student123",
            "roll_no": "2022MECH055",
            "branch": "Mechanical & Mechatronics",
            "year": "4th Year (2026)",
            "cgpa": 8.35,
            "phone": "+91 95555 44444",
            "skills": "Robotics, ROS, C++, MATLAB, Python, Embedded Control",
            "bio": "Robotics enthusiast passionate about autonomous navigation and industrial automation systems.",
            "profile_pic": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=150&auto=format&fit=crop&q=80"
        },
        {
            "name": "Ananya Verma",
            "email": "ananya@campus.com",
            "password": "student123",
            "roll_no": "2022CSE210",
            "branch": "Computer Science & Engineering",
            "year": "4th Year (2026)",
            "cgpa": 8.95,
            "phone": "+91 94444 33333",
            "skills": "React, TypeScript, GraphQL, Node.js, UI/UX, Cloud",
            "bio": "Frontend perfectionist building performant, accessible, and delightful web products.",
            "profile_pic": "https://images.unsplash.com/photo-1580489944761-15a19d654956?w=150&auto=format&fit=crop&q=80"
        }
    ]

    student_id_map = {}
    for s in sample_students:
        cursor.execute("SELECT id FROM users WHERE email = %s", (s["email"],))
        existing_u = cursor.fetchone()
        if existing_u:
            uid = existing_u["id"]
        else:
            cursor.execute("""
                INSERT INTO users (name, email, password, role, profile_pic)
                VALUES (%s, %s, %s, %s, %s)
            """, (s["name"], s["email"], s["password"], "student", s["profile_pic"]))
            uid = cursor.lastrowid

        cursor.execute("SELECT id FROM students WHERE user_id = %s", (uid,))
        existing_s = cursor.fetchone()
        if existing_s:
            sid = existing_s["id"]
        else:
            cursor.execute("""
                INSERT INTO students (user_id, roll_no, branch, year, cgpa, phone, skills, bio)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (uid, s["roll_no"], s["branch"], s["year"], s["cgpa"], s["phone"], s["skills"], s["bio"]))
            sid = cursor.lastrowid
        student_id_map[s["email"]] = sid

    # 4. Rich Sample Jobs / Recruitment Drives Across All 20 Companies
    sample_jobs = [
        {
            "company": "Google",
            "title": "Software Engineer - Full Stack & Cloud",
            "description": "As a Software Engineer at Google, you will build next-generation applications and scalable infrastructure serving billions of global users. You will collaborate across engineering, product, and design teams to create intuitive and high-impact web and mobile experiences.",
            "eligibility": "B.Tech/M.Tech in CSE/IT/ECE, Minimum 8.0 CGPA, No Active Backlogs",
            "salary": "₹24 - 30 LPA",
            "location": "Bangalore / Hybrid",
            "job_type": "Full Time",
            "skills": "Python, Go, JavaScript, React, Cloud Systems, Algorithms",
            "deadline": "2026-10-15"
        },
        {
            "company": "Microsoft",
            "title": "Azure Cloud & DevOps Systems Engineer",
            "description": "Microsoft is seeking high-potential engineering graduates to join the Azure Cloud team. You will be responsible for designing automated deployment pipelines, managing microservices orchestration, and building resilient distributed cloud systems.",
            "eligibility": "B.Tech in CSE/IT/ECE, Minimum 7.5 CGPA",
            "salary": "₹20 - 26 LPA",
            "location": "Hyderabad / Noida",
            "job_type": "Full Time",
            "skills": "Azure, Docker, Kubernetes, Linux, Python, CI/CD Pipelines",
            "deadline": "2026-10-20"
        },
        {
            "company": "Amazon",
            "title": "SDE-1 (Backend & Distributed Systems)",
            "description": "Amazon is hiring Software Development Engineers (SDE-1) for its core e-commerce and AWS services teams. Work on ultra-low latency web services, transactional databases, and scalable distributed architectures.",
            "eligibility": "B.Tech CSE/IT/ECE, Minimum 7.5 CGPA",
            "salary": "₹18 - 22 LPA",
            "location": "Hyderabad",
            "job_type": "Full Time",
            "skills": "Java, C++, Object Oriented Design, AWS, DynamoDB, REST APIs",
            "deadline": "2026-10-30"
        },
        {
            "company": "Apple",
            "title": "iOS Platform & Core OS Software Engineer",
            "description": "Join Apple's Core Operating Systems team in Hyderabad. Develop system-level software, optimize kernel performance, and build next-generation platform services that power iOS, macOS, watchOS, and visionOS devices worldwide.",
            "eligibility": "B.Tech/M.Tech in CSE/IT/ECE, Minimum 8.0 CGPA",
            "salary": "₹26 - 34 LPA",
            "location": "Hyderabad",
            "job_type": "Full Time",
            "skills": "Swift, Objective-C, C++, Data Structures, OS Internals, Concurrency",
            "deadline": "2026-11-01"
        },
        {
            "company": "Goldman Sachs",
            "title": "Quantitative Software & Algorithmic Analyst",
            "description": "Join our Engineering division to develop high-performance financial computation engines, quantitative analytics tools, and algorithmic execution models. Great opportunity for problem solvers who love mathematics and ultra-low latency code.",
            "eligibility": "B.Tech/Dual Degree All Engineering Branches, Minimum 8.5 CGPA",
            "salary": "₹22 - 28 LPA",
            "location": "Bangalore",
            "job_type": "Full Time",
            "skills": "C++, Algorithms, Linear Algebra, Probability, Multi-threading",
            "deadline": "2026-11-05"
        },
        {
            "company": "Adobe",
            "title": "Creative Cloud & Computer Vision Engineer",
            "description": "Adobe is looking for dynamic graduates to join our Creative Cloud and AI research teams. You will engineer image processing pipelines, deep learning vision models, and web technologies powering Photoshop, Premiere, and Firefly.",
            "eligibility": "B.Tech in CSE/IT, Minimum 7.8 CGPA",
            "salary": "₹22 - 28 LPA",
            "location": "Noida & Bangalore",
            "job_type": "Full Time",
            "skills": "C++, Python, WebGL, Computer Vision, Deep Learning, React",
            "deadline": "2026-10-25"
        },
        {
            "company": "Salesforce",
            "title": "Cloud Platform & Distributed Software Engineer",
            "description": "Build high-throughput multitenant architecture at Salesforce. Selected candidates will design distributed caching systems, microservices APIs, and secure cloud platforms handling trillions of transactions monthly.",
            "eligibility": "B.Tech CSE/IT, Minimum 7.5 CGPA",
            "salary": "₹20 - 25 LPA",
            "location": "Hyderabad & Bangalore",
            "job_type": "Full Time",
            "skills": "Java, Spring, Apex, Distributed Systems, Kafka, AWS",
            "deadline": "2026-11-12"
        },
        {
            "company": "Oracle",
            "title": "Autonomous Database & Cloud Infrastructure Engineer",
            "description": "Work on the cutting edge of cloud database technology at Oracle Cloud Infrastructure (OCI). Develop autonomous indexing algorithms, query optimizers, and automated disaster recovery platforms.",
            "eligibility": "B.Tech/M.Tech in CSE/IT/ECE, Minimum 7.2 CGPA",
            "salary": "₹18 - 24 LPA",
            "location": "Bangalore & Hyderabad",
            "job_type": "Full Time",
            "skills": "C++, Java, SQL, Linux Kernel, Distributed Storage, Networking",
            "deadline": "2026-11-18"
        },
        {
            "company": "Cisco Systems",
            "title": "Cybersecurity & Core Network Software Engineer",
            "description": "Cisco is hiring engineers to build secure next-generation SD-WAN, firewall protection algorithms, and zero-trust cloud architectures. Protect enterprise data and power global internet backbones.",
            "eligibility": "B.Tech in CSE/IT/ECE, Minimum 7.5 CGPA",
            "salary": "₹16 - 22 LPA",
            "location": "Bangalore",
            "job_type": "Full Time",
            "skills": "Python, C, TCP/IP, Cryptography, Network Security, Linux",
            "deadline": "2026-11-15"
        },
        {
            "company": "Uber Technologies",
            "title": "SDE-1 (High-Scale Mobility & Real-Time Logistics)",
            "description": "Work on the marketplace algorithms that match riders, drivers, and deliveries globally. Tackle challenges in real-time geospatial routing, surge pricing dynamics, and fault-tolerant streaming data pipelines.",
            "eligibility": "B.Tech in CSE/IT, Minimum 8.0 CGPA",
            "salary": "₹28 - 36 LPA",
            "location": "Bangalore & Hyderabad",
            "job_type": "Full Time",
            "skills": "Go, Java, Microservices, Kafka, Redis, Distributed Systems",
            "deadline": "2026-10-28"
        },
        {
            "company": "Qualcomm",
            "title": "5G Modem & Embedded Systems Firmware Engineer",
            "description": "Develop low-level embedded software and DSP algorithms for Snapdragon processors and 5G basebands. Work closely with hardware engineering teams to optimize silicon power efficiency and wireless throughput.",
            "eligibility": "B.Tech/M.Tech in ECE/EEE/CSE, Minimum 7.5 CGPA",
            "salary": "₹18 - 25 LPA",
            "location": "Hyderabad & Chennai",
            "job_type": "Full Time",
            "skills": "C, Embedded Systems, RTOS, ARM Architecture, 5G Protocols, Device Drivers",
            "deadline": "2026-11-08"
        },
        {
            "company": "Morgan Stanley",
            "title": "Technology & Algorithmic FinTech Analyst",
            "description": "Design institutional trading applications, market data feeds, and wealth management platforms. Collaborate with global trading desks in New York, London, and Tokyo to deliver millisecond-level execution software.",
            "eligibility": "B.Tech All Disciplines, Minimum 8.0 CGPA",
            "salary": "₹20 - 27 LPA",
            "location": "Mumbai & Bangalore",
            "job_type": "Full Time",
            "skills": "Java, C++, Spring Boot, SQL, Financial Markets, Distributed Caching",
            "deadline": "2026-11-20"
        },
        {
            "company": "Intel Corporation",
            "title": "SoC Software & AI Acceleration Systems Engineer",
            "description": "Join Intel's software development group. Write low-level device drivers, compiler toolchains, and AI acceleration libraries (OpenVINO) for next-generation Intel Core Ultra and Xeon processors.",
            "eligibility": "B.Tech/M.Tech in CSE/ECE, Minimum 7.5 CGPA",
            "salary": "₹17 - 23 LPA",
            "location": "Bangalore",
            "job_type": "Full Time",
            "skills": "C, C++, Computer Architecture, Python, Deep Learning Acceleration, Linux",
            "deadline": "2026-11-22"
        },
        {
            "company": "Flipkart",
            "title": "SDE-1 (Supply Chain & High-Throughput E-Commerce)",
            "description": "Scale India's most loved shopping platform. Build inventory management microservices, real-time recommendation engines, and fault-tolerant checkout pipelines capable of handling million-QPS Big Billion Day sales.",
            "eligibility": "B.Tech CSE/IT, Minimum 7.2 CGPA",
            "salary": "₹18 - 24 LPA",
            "location": "Bangalore",
            "job_type": "Full Time",
            "skills": "Java, Spring Boot, MySQL, Elasticsearch, Cassandra, Kafka",
            "deadline": "2026-11-10"
        },
        {
            "company": "Atlassian",
            "title": "Full Stack Product Engineer (Jira & Confluence)",
            "description": "Atlassian builds software products that empower millions of teams worldwide. Join our engineering team to design modern web interfaces in React/TypeScript and scalable GraphQL backend microservices.",
            "eligibility": "B.Tech CSE/IT, Minimum 7.5 CGPA",
            "salary": "₹24 - 32 LPA",
            "location": "Remote & Bangalore",
            "job_type": "Full Time",
            "skills": "JavaScript, TypeScript, React, Node.js, GraphQL, AWS",
            "deadline": "2026-10-31"
        },
        {
            "company": "Netflix",
            "title": "Video Streaming Infrastructure & Core Performance Engineer",
            "description": "Work on the global Open Connect content delivery network and backend infrastructure delivering seamless 4K HDR streaming to over 260 million global households. Optimize video encoding and network congestion control.",
            "eligibility": "B.Tech/M.Tech in CSE/IT/ECE, Minimum 8.2 CGPA",
            "salary": "₹32 - 40 LPA",
            "location": "Mumbai & Remote",
            "job_type": "Full Time",
            "skills": "Go, C++, Java, Distributed Systems, Video Codecs, Networking",
            "deadline": "2026-10-18"
        },
        {
            "company": "Tata Consultancy Services (TCS)",
            "title": "TCS Digital - AI, ML & Software Systems Developer",
            "description": "TCS Digital is the premier talent intake drive for ambitious engineering graduates. Selected candidates lead cutting-edge client transformation projects in generative AI, enterprise cloud migration, and IoT analytics.",
            "eligibility": "B.Tech/M.Tech All Disciplines, Minimum 7.0 CGPA",
            "salary": "₹8.5 - 11 LPA",
            "location": "Pune, Mumbai & Hyderabad",
            "job_type": "Full Time",
            "skills": "Python, Machine Learning, Java, Cloud, SQL, Problem Solving",
            "deadline": "2026-11-15"
        },
        {
            "company": "Infosys",
            "title": "Specialist Programmer (Power Programmer)",
            "description": "The Specialist Programmer role at Infosys is an elite competitive coding cadre. Candidates work directly on high-complexity architecture, full-stack microservices, and specialized deep-tech engineering.",
            "eligibility": "B.Tech/M.Tech/MCA, Minimum 7.0 CGPA",
            "salary": "₹9.5 - 13 LPA",
            "location": "Bangalore & Mysore",
            "job_type": "Full Time",
            "skills": "Competitive Programming, Java, Spring Boot, Node.js, Cloud, DevOps",
            "deadline": "2026-11-10"
        },
        {
            "company": "IBM India",
            "title": "Quantum Computing & Hybrid Cloud Developer",
            "description": "Join IBM Software Labs to develop Red Hat OpenShift solutions, enterprise cloud automations, and explore quantum algorithms on IBM Qiskit platforms. Great mentorship and global product exposure.",
            "eligibility": "B.Tech in CSE/IT/ECE, Minimum 7.0 CGPA",
            "salary": "₹12 - 16 LPA",
            "location": "Bangalore & Pune",
            "job_type": "Full Time",
            "skills": "Python, Linux, Docker, Kubernetes, Cloud Architecture, Java",
            "deadline": "2026-11-25"
        },
        {
            "company": "Wipro Technologies",
            "title": "Wipro Turbo - Next-Gen Full Stack Specialist",
            "description": "Wipro Turbo is the premier hiring program for engineering graduates with strong algorithmic fundamentals. Work with Fortune 500 enterprise clients across banking, retail, healthcare, and automotive technologies.",
            "eligibility": "B.Tech All Engineering Branches, Minimum 7.0 CGPA",
            "salary": "₹7.5 - 9.5 LPA",
            "location": "Bangalore & Hyderabad",
            "job_type": "Full Time",
            "skills": "Java, Python, React, Data Structures, Cloud Fundamentals, REST APIs",
            "deadline": "2026-11-30"
        }
    ]

    job_ids = []
    for j in sample_jobs:
        cid = company_id_map.get(j["company"])
        if cid:
            cursor.execute("SELECT id FROM jobs WHERE company_id = %s AND title = %s", (cid, j["title"]))
            existing_job = cursor.fetchone()
            if existing_job:
                job_ids.append(existing_job["id"])
            else:
                cursor.execute("""
                    INSERT INTO jobs (company_id, title, description, eligibility, salary, location, job_type, skills, deadline)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (cid, j["title"], j["description"], j["eligibility"], j["salary"], j["location"], j["job_type"], j["skills"], j["deadline"]))
                job_ids.append(cursor.lastrowid)

    # 5. Realistic Pre-Seeded Applications for Student Dashboards
    if job_ids and student_id_map:
        student1_id = student_id_map.get("student@campus.com")
        student2_id = student_id_map.get("priya@campus.com")
        student3_id = student_id_map.get("amit@campus.com")
        student4_id = student_id_map.get("sneha@campus.com")

        # Rahul Applications
        if student1_id and len(job_ids) >= 4:
            for jid, status in [(job_ids[0], "Shortlisted"), (job_ids[2], "Applied"), (job_ids[9], "Applied"), (job_ids[14], "Selected")]:
                cursor.execute("SELECT id FROM applications WHERE job_id = %s AND student_id = %s", (jid, student1_id))
                if not cursor.fetchone():
                    cursor.execute("INSERT INTO applications (job_id, student_id, status) VALUES (%s, %s, %s)", (jid, student1_id, status))

        # Priya Applications
        if student2_id and len(job_ids) >= 3:
            for jid, status in [(job_ids[1], "Selected"), (job_ids[3], "Shortlisted")]:
                cursor.execute("SELECT id FROM applications WHERE job_id = %s AND student_id = %s", (jid, student2_id))
                if not cursor.fetchone():
                    cursor.execute("INSERT INTO applications (job_id, student_id, status) VALUES (%s, %s, %s)", (jid, student2_id, status))

        # Sneha Applications
        if student4_id and len(job_ids) >= 5:
            for jid, status in [(job_ids[4], "Selected"), (job_ids[5], "Shortlisted")]:
                cursor.execute("SELECT id FROM applications WHERE job_id = %s AND student_id = %s", (jid, student4_id))
                if not cursor.fetchone():
                    cursor.execute("INSERT INTO applications (job_id, student_id, status) VALUES (%s, %s, %s)", (jid, student4_id, status))

    db.commit()
    cursor.close()
