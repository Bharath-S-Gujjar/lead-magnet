# Lead Magnet — Deployment Guide

---

## 1. Deployment Topology

Lead Magnet is designed as a cloud-native decoupled architecture:

```
[ Vercel / Netlify ] ---------> [ Render / Railway / AWS ] ---------> [ MongoDB Atlas ]
  User Portal (React)             Flask Backend Service                 M0 / Dedicated Cluster
  Admin Portal (React)            Gunicorn + Eventlet (WebSockets)      ReplicaSet TLS
```

---

## 2. Backend Deployment (Render / Heroku / Container)

### 2.1 Web Process Configuration
The backend uses Gunicorn with Eventlet workers for concurrent HTTP requests and real-time Socket.IO streams:
```text
web: gunicorn app:app --worker-class eventlet -w 1 --bind 0.0.0.0:$PORT
```
(Configured in [`backend/Procfile`](file:///d:/lead-magnet/backend/Procfile) and [`backend/render.yaml`](file:///d:/lead-magnet/backend/render.yaml)).

### 2.2 Required Environment Variables
Configure the following in your hosting provider's dashboard:

| Variable | Description | Example / Recommended Value |
| :--- | :--- | :--- |
| `PORT` | Service binding port | `5000` |
| `FLASK_ENV` | Environment mode | `production` |
| `MONGO_URI` | MongoDB Atlas Connection String | `mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true&w=majority` |
| `MONGO_DB_NAME` | Authoritative Database Name | `leadmagnet` |
| `JWT_SECRET` | Strong secret for signing auth tokens | *Secure 64-char hex string* |
| `CLIENT_URL` | User Portal URL (for CORS) | `https://store.leadmagnet.app` |
| `ADMIN_URL` | Admin Portal URL (for CORS) | `https://admin.leadmagnet.app` |

---

## 3. Frontend Deployment (Vercel / Cloudflare Pages)

### 3.1 Admin Intelligence Portal (`frontend/admin`)
- **Build Command**: `npm run build`
- **Output Directory**: `dist`
- **Environment Variables**:
  - `VITE_API_URL`: `https://api.yourdomain.com`

### 3.2 Customer Store Portal (`frontend/user`)
- **Build Command**: `npm run build`
- **Output Directory**: `dist`
- **Environment Variables**:
  - `VITE_API_URL`: `https://api.yourdomain.com`

---

## 4. Database Security & Atlas Configuration

1. **IP Access List**:
   - Ensure the server host's outbound IP is whitelisted under **Atlas Console $\rightarrow$ Network Access**.
2. **TLS / SSL**:
   - Python connects using `certifi.where()` to guarantee valid CA validation across all Linux/Windows environments.
3. **Database Indexes**:
   - All critical indexes (`product_id_1`, `category_1`, `gender_1`, `brand_1`, `price_1`) are created automatically and verified on service startup.
