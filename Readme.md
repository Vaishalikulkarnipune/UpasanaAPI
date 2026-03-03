<!-- ================= For Internal Team ================= -->
<!-- **Windows Command**
flask run --host=0.0.0.0 --port=5000
**Linux Server command**
gunicorn app:app -w 4 -b 0.0.0.0:5000

**After changes add new dependencies into requirement.txt**
pip freeze > requirements.txt

**How to Install required Python libraries**
**Goto API Folder**
pip install -r requirements.txt


**How to Open Python service to be accessible from Expo App**
---DONT FORGET TO RESTART PYTHON SERVICE ONCE CHANGES ARE APPLIED
---PLEASE VERIFY BY USING IP BASED URL FROM BROWSER
--- LIKE http://192.168.1.9:5000/users
**CHATGPT PROMPT**
I have started my python service like python app.py
help me to make sure that service is accissibleby IP

**Firewall and Network Settings**
Ensure that your machine's firewall is not blocking incoming connections to the Flask service. On different platforms, you may need to configure this differently:

**For Linux (Ubuntu) Firewall:**
Use ufw to allow the port (e.g., 5000):

bash
Copy code
sudo ufw allow 5000/tcp

**For Windows Firewall:**
Go to Control Panel > System and Security > Windows Defender Firewall.
Click on Advanced settings.
In the left pane, click Inbound Rules, then New Rule... in the right pane.
Select Port, then specify TCP and the port you are using (e.g., 5000).
Follow the steps to allow connections.
**For macOS Firewall:**
Go to System Preferences > Security & Privacy > Firewall.
If the firewall is on, click the lock icon to make changes.
Click Firewall Options, then allow incoming connections for Python or specify the port.
**Start the Flask App**
Now, run your Flask app again using:

bash
Copy code
python app.py
This will start the Flask app and bind it to 0.0.0.0, making it accessible over the network.

**Access Flask Service via IP**
To access the Flask service from another device on your network, use the IP address of the machine where Flask is running, followed by the port.

For example, if the IP of your machine is 192.168.1.100 and Flask is running on port 5000, access the service like this:

bash
Copy code
http://192.168.1.100:5000 --!>


<!-- ================= For Internal Team Discussion End ================= -->

# 🛕 Ramdasi Bana  
### Devotional Booking & Member Management System

A production-ready backend system built using **Flask and PostgreSQL** to manage devotional member registrations, structured booking workflows, and administrative analytics.

This project demonstrates strong backend engineering fundamentals including relational database modeling, validation logic design, booking state management, and production deployment readiness.

---

## 🚀 Project Overview

Upasana API is a structured backend system designed to handle:

- Member registration & authentication
- Zone-based validation using pincode logic
- Booking lifecycle management
- Booking lock control to prevent conflicts
- Administrative summary insights
- Aggregated relational data retrieval
- Load validation & duplicate prevention mechanisms

The system is designed with clean architecture principles and production scalability in mind.

---

## 🎯 Business Logic & Engineering Highlights

### 🔐 Secure User Flow
- Mobile-based registration & login
- Duplicate prevention at database level
- Input validation & integrity checks

### 📍 Zone-Based Validation Engine
- Pincode → Zone mapping enforcement
- Booking eligibility validation
- Structured error handling

### 📅 Intelligent Booking Management
- Active / Inactive booking states
- Automatic booking lock removal on cancellation
- Conflict prevention logic
- Ownership verification before updates

### 📊 Administrative Analytics
- Summary aggregation APIs
- User-to-booking relational joins
- Structured JSON responses optimized for dashboard integration

### 🧪 Reliability & Testing
- Load testing scripts
- Duplicate booking validation tests
- Health check endpoint for deployment monitoring

---

## 🛠 Tech Stack

- **Backend:** Flask (Python)
- **Database:** PostgreSQL
- **ORM:** SQLAlchemy
- **Server:** Gunicorn
- **Testing:** Custom validation scripts
- **Deployment Ready:** Linux server compatible

---

## 🏗 Architecture & Design Approach

- Stateless RESTful design
- Relational database normalization
- Centralized configuration management
- Structured error handling with HTTP status codes
- Production-grade server configuration
- Designed for future JWT-based authentication integration
- Easily extendable to microservices architecture

---

## 📈 Scalability Considerations

- Ready for Docker containerization
- Can integrate Redis for booking lock optimization
- Supports horizontal scaling via Gunicorn workers
- Easily extendable for admin dashboard frontend integration
- Modular design for adding new devotional events

---

## 📸 Screenshots

<!-- SCREENSHOT: User Registration API Response -->

<!-- SCREENSHOT: Booking Creation Flow -->

<!-- SCREENSHOT: Sunday Booking Aggregated Data -->

<!-- SCREENSHOT: Admin Summary Dashboard Response -->

<!-- SCREENSHOT: Database Schema Diagram -->

---

## 🏆 Key Learning Outcomes

Through this project, I demonstrated:

- Real-world backend workflow design
- Relational data modeling expertise
- Conflict prevention logic implementation
- Scalable API architecture design
- Production deployment understanding
- Performance validation & system reliability testing

---

## ⚙️ Installation & Setup

###  Clone the Repository

```bash
git clone https://github.com/your-username/upasana-api.git
cd upasana-api
```

### Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # For Linux / Mac
# venv\Scripts\activate   # For Windows
```

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Configure Environment Variables
```bash
DATABASE_URL=your_postgresql_connection_string
SECRET_KEY=your_secret_key
```

### Run the Application
```bash
python app.py
```

#### Application runs locally on 
```bash
http://localhost:5000
```
