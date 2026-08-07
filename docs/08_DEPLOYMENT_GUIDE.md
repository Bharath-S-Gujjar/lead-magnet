# Lead Magnet - Deployment Guide

> This document explains how to set up, run, and deploy the Lead Magnet project for development and production.

---

# Project Structure

```
lead-magnet/

├── backend/
├── frontend/
│   ├── user/
│   └── admin/
├── model/
├── data/
├── notebooks/
├── docs/
└── README.md
```

---

# Technology Stack

## Backend

- Python 3.14+
- Flask
- Flask-SocketIO
- PyMongo
- JWT
- Bcrypt

---

## Frontend

- React
- Vite
- React Router
- Context API

---

## Machine Learning

- Scikit-Learn
- XGBoost
- KMeans
- Joblib

---

## Database

MongoDB Atlas

---

# Local Development Requirements

Install the following:

- Python 3.14+
- Node.js
- npm
- Git
- MongoDB Atlas Account
- VS Code
- Postman

---

# Python Environment

Create a virtual environment.

Windows

```bash
py -m venv venv
```

Activate

PowerShell

```powershell
.\venv\Scripts\Activate.ps1
```

Command Prompt

```cmd
venv\Scripts\activate
```

---

# Install Backend Dependencies

```bash
pip install -r requirements.txt
```

If no requirements file exists

```bash
pip install flask
pip install flask-cors
pip install flask-socketio
pip install pymongo
pip install bcrypt
pip install pyjwt
pip install python-dotenv
pip install pandas
pip install numpy
pip install scikit-learn
pip install xgboost
pip install joblib
```

---

# Install Frontend Dependencies

User Portal

```bash
cd frontend/user
npm install
```

Admin Portal

```bash
cd frontend/admin
npm install
```

---

# MongoDB Atlas

Create

- Free Cluster

Create

- Database User

Allow

```
0.0.0.0/0
```

Copy connection string

```
mongodb+srv://...
```

---

# Environment Variables

Create

```
backend/.env
```

Example

```env
MONGO_URI=mongodb+srv://<username>:<password>@cluster.mongodb.net/

JWT_SECRET=your-secret-key

ADMIN_USERNAME=admin

ADMIN_PASSWORD=admin123
```

Never commit the `.env` file.

---

# Running Backend

From

```
backend/
```

Run

```bash
python app.py
```

Default

```
http://localhost:5000
```

---

# Running User Frontend

```
cd frontend/user
```

```bash
npm run dev
```

Default

```
http://localhost:3001
```

---

# Running Admin Frontend

```
cd frontend/admin
```

```bash
npm run dev
```

Default

```
http://localhost:5173
```

(Vite may assign a different port if 5173 is unavailable.)

---

# Local Development Flow

Start services in this order.

1.

MongoDB Atlas

↓

Connected

2.

Backend

↓

Flask

3.

User Frontend

↓

React

4.

Admin Frontend

↓

React

---

# Testing APIs

Use

- Postman

or

- Thunder Client

Test order

1.

Signup

↓

2.

Login

↓

3.

Products

↓

4.

Session Start

↓

5.

Session Event

↓

6.

Session End

↓

7.

Admin Login

↓

8.

Dashboard APIs

---

# Machine Learning Models

Stored inside

```
model/
```

Files

```
xgb_model.pkl

scaler.pkl

feature_columns.pkl

kmeans_model.pkl

segment_map.pkl
```

Do not rename these files unless the backend configuration is updated.

---

# Database Collections

Current

- users
- products
- sessions
- events
- leads

Future

- cart
- wishlist
- orders
- user_profiles
- campaigns
- campaign_logs

---

# Deployment Plan

## Backend

Recommended

Render

Deployment steps

- Push backend to GitHub
- Create Render Web Service
- Configure environment variables
- Deploy

---

## Frontend

Recommended

Vercel

Deployment steps

User Portal

↓

Vercel Project

Admin Portal

↓

Separate Vercel Project

---

## Database

MongoDB Atlas

Shared by all deployed services.

---

# Production Checklist

Before deployment

- Disable Flask debug mode
- Configure production CORS
- Use secure JWT secret
- Verify MongoDB connection
- Remove hardcoded credentials
- Configure environment variables
- Test admin authentication
- Test ML pipeline
- Test frontend integration

---

# Future Infrastructure

Future improvements may include

- APScheduler
- Celery
- Redis
- Docker
- Nginx
- GitHub Actions
- CI/CD Pipeline

---

# Backup Strategy

Maintain backups of

- MongoDB Atlas
- Machine Learning models
- Documentation
- GitHub repository

Never store production secrets inside Git.

---

# Repository Workflow

Recommended Git workflow

```bash
git pull

git checkout -b feature/<feature-name>

git add .

git commit -m "feat: implement feature"

git push origin feature/<feature-name>
```

Merge after review.

---

# Documentation

Before implementing any major feature

Read

1. docs/01_MASTER_CONTEXT.md

2. docs/02_DATABASE_SCHEMA.md

3. docs/03_API_CONTRACT.md

4. docs/04_PROJECT_ROADMAP.md

5. docs/05_CODING_GUIDELINES.md

6. docs/06_FRONTEND_INTEGRATION.md

7. docs/07_SYSTEM_ARCHITECTURE.md

8. docs/08_DEPLOYMENT_GUIDE.md

These documents are the official source of truth for the project.

---

# Current Project Status

Backend

✅ Stable

Machine Learning

✅ Stable

Database

✅ Stable

Authentication

✅ Stable

Documentation

✅ Complete

Frontend Integration

🚧 In Progress

Recommendation Engine

🚧 Planned

Marketing Automation

🚧 Planned

Deployment

🚧 Pending

---

End of Deployment Guide.